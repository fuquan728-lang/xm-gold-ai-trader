#!/usr/bin/env python3
"""
PPO强化学习训练器 — 交易策略Agent训练

架构: Actor-Critic with PPO clipping
- Actor网络: obs → action logits
- Critic网络: obs → state value
- 支持: GAE优势估计, 多epoch更新, 熵正则化

与现有系统集成:
- 训练后的模型可替代/增强LLM决策
- 使用backtest_engine进行样本外回测验证
"""

import os
import json
import time
import pickle
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field

import numpy as np

from core.logger import logger

# PyTorch为可选依赖
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.optim as optim
    from torch.distributions import Categorical
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("[RL] PyTorch not available, using NumPy-only fallback mode")


# ==================== PyTorch神经网络 ====================

if TORCH_AVAILABLE:

    class ActorCritic(nn.Module):
        """Actor-Critic网络"""

        def __init__(self, obs_dim: int, n_actions: int, 
                     hidden_dim: int = 128, n_layers: int = 2):
            super().__init__()

            layers = []
            in_dim = obs_dim
            for i in range(n_layers):
                layers.append(nn.Linear(in_dim, hidden_dim))
                layers.append(nn.LayerNorm(hidden_dim))
                layers.append(nn.ReLU())
                in_dim = hidden_dim

            self.shared = nn.Sequential(*layers)

            # Actor head
            self.actor = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, n_actions)
            )

            # Critic head
            self.critic = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, 1)
            )

            # 权重初始化
            self.apply(self._init_weights)

        def _init_weights(self, module):
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
                nn.init.constant_(module.bias, 0.0)

        def forward(self, x):
            shared_out = self.shared(x)
            action_logits = self.actor(shared_out)
            value = self.critic(shared_out)
            return action_logits, value

        def get_action(self, obs: np.ndarray, deterministic: bool = False):
            """获取动作"""
            with torch.no_grad():
                obs_tensor = torch.FloatTensor(obs).unsqueeze(0)
                logits, value = self.forward(obs_tensor)
                probs = F.softmax(logits, dim=-1)

                if deterministic:
                    action = torch.argmax(probs, dim=-1).item()
                    log_prob = torch.log(probs[0, action]).item()
                else:
                    dist = Categorical(probs)
                    action = dist.sample().item()
                    log_prob = dist.log_prob(torch.tensor(action)).item()

                return action, log_prob, value.item()

        def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor):
            """批量评估动作的对数概率和熵"""
            logits, values = self.forward(obs)
            probs = F.softmax(logits, dim=-1)
            dist = Categorical(probs)

            action_log_probs = dist.log_prob(actions)
            entropy = dist.entropy().mean()

            return action_log_probs, entropy, values.squeeze(-1)


    # ==================== PPO训练器 ====================

    @dataclass
    class PPOHyperparams:
        """PPO超参数"""
        learning_rate: float = 3e-4
        n_epochs: int = 10
        batch_size: int = 64
        gamma: float = 0.99           # 折扣因子
        gae_lambda: float = 0.95      # GAE平滑参数
        clip_epsilon: float = 0.2     # PPO clip范围
        value_coef: float = 0.5       # 价值损失系数
        entropy_coef: float = 0.01    # 熵正则系数
        max_grad_norm: float = 0.5    # 梯度裁剪
        hidden_dim: int = 128
        n_layers: int = 2
        device: str = "cpu"

    @dataclass
    class RolloutBuffer:
        """经验回放缓冲区"""
        obs: List[np.ndarray] = field(default_factory=list)
        actions: List[int] = field(default_factory=list)
        log_probs: List[float] = field(default_factory=list)
        rewards: List[float] = field(default_factory=list)
        values: List[float] = field(default_factory=list)
        dones: List[bool] = field(default_factory=list)

        def add(self, obs, action, log_prob, reward, value, done):
            self.obs.append(obs.copy())
            self.actions.append(action)
            self.log_probs.append(log_prob)
            self.rewards.append(reward)
            self.values.append(value)
            self.dones.append(done)

        def clear(self):
            self.obs.clear()
            self.actions.clear()
            self.log_probs.clear()
            self.rewards.clear()
            self.values.clear()
            self.dones.clear()

        def __len__(self):
            return len(self.obs)


    class PPOTrainer:
        """PPO训练器"""

        def __init__(self, obs_dim: int, n_actions: int,
                     hyperparams: PPOHyperparams = None):
            self.obs_dim = obs_dim
            self.n_actions = n_actions
            self.hp = hyperparams or PPOHyperparams()

            # 网络
            self.model = ActorCritic(
                obs_dim, n_actions,
                hidden_dim=self.hp.hidden_dim,
                n_layers=self.hp.n_layers
            ).to(self.hp.device)

            self.optimizer = optim.Adam(
                self.model.parameters(), lr=self.hp.learning_rate
            )

            # 缓冲区
            self.buffer = RolloutBuffer()

            # 训练统计
            self.train_steps = 0
            self.episode_rewards: List[float] = []
            self.loss_history: List[float] = []

            logger.info(f"[PPO] Trainer initialized: obs_dim={obs_dim}, "
                        f"actions={n_actions}, device={self.hp.device}")

        def collect_trajectory(self, env, n_steps: int = 2048) -> Dict:
            """收集轨迹数据"""
            obs = env.reset()
            episode_reward = 0.0
            n_episodes = 0
            total_steps = 0

            for step in range(n_steps):
                obs_tensor = torch.FloatTensor(obs).unsqueeze(0).to(self.hp.device)
                with torch.no_grad():
                    logits, value = self.model(obs_tensor)
                    probs = F.softmax(logits, dim=-1)
                    dist = Categorical(probs)
                    action = dist.sample().item()
                    log_prob = dist.log_prob(torch.tensor(action).to(self.hp.device)).item()

                next_obs, reward, terminated, truncated, info = env.step(action)
                done = terminated or truncated

                self.buffer.add(obs, action, log_prob, reward, value.item(), done)
                episode_reward += reward

                obs = next_obs
                total_steps += 1

                if done:
                    self.episode_rewards.append(episode_reward)
                    n_episodes += 1
                    episode_reward = 0.0
                    obs = env.reset()

            return {
                "steps_collected": total_steps,
                "n_episodes": n_episodes,
                "avg_reward": np.mean(self.episode_rewards[-n_episodes:]) if n_episodes > 0 else 0
            }

        def compute_gae(self, last_value: float = 0.0) -> Tuple[np.ndarray, np.ndarray]:
            """计算GAE优势估计和回报"""
            n = len(self.buffer)
            advantages = np.zeros(n, dtype=np.float32)
            returns = np.zeros(n, dtype=np.float32)

            gae = 0.0
            next_value = last_value

            for t in reversed(range(n)):
                if self.buffer.dones[t]:
                    delta = self.buffer.rewards[t] - self.buffer.values[t]
                    gae = 0.0
                else:
                    delta = self.buffer.rewards[t] + self.hp.gamma * next_value - self.buffer.values[t]
                    gae = delta + self.hp.gamma * self.hp.gae_lambda * gae

                advantages[t] = gae
                returns[t] = gae + self.buffer.values[t]
                next_value = self.buffer.values[t]

            # 标准化advantages
            advantages = (advantages - np.mean(advantages)) / (np.std(advantages) + 1e-8)

            return advantages, returns

        def update(self) -> Dict:
            """PPO更新步骤"""
            if len(self.buffer) == 0:
                return {}

            # 计算GAE
            advantages, returns = self.compute_gae()

            # 转换为tensor
            obs_tensor = torch.FloatTensor(np.array(self.buffer.obs)).to(self.hp.device)
            actions_tensor = torch.LongTensor(self.buffer.actions).to(self.hp.device)
            old_log_probs = torch.FloatTensor(self.buffer.log_probs).to(self.hp.device)
            advantages_tensor = torch.FloatTensor(advantages).to(self.hp.device)
            returns_tensor = torch.FloatTensor(returns).to(self.hp.device)

            total_policy_loss = 0.0
            total_value_loss = 0.0
            total_entropy = 0.0
            n_updates = 0

            n_samples = len(self.buffer)
            indices = np.arange(n_samples)

            for epoch in range(self.hp.n_epochs):
                np.random.shuffle(indices)

                for start in range(0, n_samples, self.hp.batch_size):
                    end = min(start + self.hp.batch_size, n_samples)
                    batch_idx = indices[start:end]

                    batch_obs = obs_tensor[batch_idx]
                    batch_actions = actions_tensor[batch_idx]
                    batch_old_log_probs = old_log_probs[batch_idx]
                    batch_advantages = advantages_tensor[batch_idx]
                    batch_returns = returns_tensor[batch_idx]

                    # 前向传播
                    new_log_probs, entropy, values = self.model.evaluate_actions(
                        batch_obs, batch_actions
                    )

                    # PPO clip loss
                    ratio = torch.exp(new_log_probs - batch_old_log_probs)
                    surr1 = ratio * batch_advantages
                    surr2 = torch.clamp(ratio, 1 - self.hp.clip_epsilon,
                                        1 + self.hp.clip_epsilon) * batch_advantages
                    policy_loss = -torch.min(surr1, surr2).mean()

                    # Value loss
                    value_loss = F.mse_loss(values, batch_returns)

                    # 总损失
                    loss = (policy_loss + 
                           self.hp.value_coef * value_loss - 
                           self.hp.entropy_coef * entropy)

                    # 反向传播
                    self.optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.model.parameters(), self.hp.max_grad_norm)
                    self.optimizer.step()

                    total_policy_loss += policy_loss.item()
                    total_value_loss += value_loss.item()
                    total_entropy += entropy.item()
                    n_updates += 1
                    self.train_steps += 1

            avg_policy_loss = total_policy_loss / n_updates if n_updates > 0 else 0
            avg_value_loss = total_value_loss / n_updates if n_updates > 0 else 0
            avg_entropy = total_entropy / n_updates if n_updates > 0 else 0

            self.loss_history.append(avg_policy_loss)

            return {
                "policy_loss": avg_policy_loss,
                "value_loss": avg_value_loss,
                "entropy": avg_entropy,
                "n_updates": n_updates
            }

        def train(self, env_factory: Callable, 
                  total_timesteps: int = 100000,
                  eval_interval: int = 10000,
                  save_path: str = None,
                  eval_env_factory: Callable = None) -> Dict:
            """
            PPO训练循环

            Args:
                env_factory: 返回训练环境的工厂函数
                total_timesteps: 总训练步数
                eval_interval: 评估间隔
                save_path: 模型保存路径
                eval_env_factory: 返回评估环境的工厂函数

            Returns:
                训练历史字典
            """
            env = env_factory()
            eval_env = eval_env_factory() if eval_env_factory else None

            history = {
                "steps": [], "avg_reward": [], "policy_loss": [],
                "eval_sharpe": [], "eval_return": [], "eval_max_dd": []
            }

            start_time = time.time()
            total_steps = 0

            logger.info(f"[PPO] Training started: {total_timesteps} steps")
            iteration = 0

            while total_steps < total_timesteps:
                # 收集轨迹
                collect_info = self.collect_trajectory(env, n_steps=2048)
                total_steps += collect_info["steps_collected"]

                # PPO更新
                update_info = self.update()
                self.buffer.clear()

                iteration += 1

                # 日志
                if iteration % 5 == 0:
                    elapsed = time.time() - start_time
                    steps_per_sec = total_steps / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"[PPO] Step {total_steps}/{total_timesteps} "
                        f"({steps_per_sec:.0f} steps/s) "
                        f"avg_reward={collect_info['avg_reward']:.2f} "
                        f"p_loss={update_info.get('policy_loss', 0):.3f}"
                    )

                # 评估
                if eval_env and total_steps % eval_interval < 2048:
                    eval_metrics = self.evaluate(eval_env)
                    logger.info(
                        f"[PPO][Eval] Sharpe={eval_metrics['sharpe']:.2f} "
                        f"Return={eval_metrics['return_pct']:.1f}% "
                        f"MaxDD={eval_metrics['max_dd_pct']:.1f}%"
                    )
                    history["eval_sharpe"].append(eval_metrics["sharpe"])
                    history["eval_return"].append(eval_metrics["return_pct"])
                    history["eval_max_dd"].append(eval_metrics["max_dd_pct"])

                history["steps"].append(total_steps)
                history["avg_reward"].append(collect_info["avg_reward"])
                history["policy_loss"].append(update_info.get("policy_loss", 0))

            elapsed = time.time() - start_time
            logger.info(f"[PPO] Training complete: {total_steps} steps in {elapsed:.1f}s")

            # 保存模型
            if save_path:
                self.save(save_path)

            return history

        def evaluate(self, env, n_episodes: int = 3) -> Dict:
            """评估当前策略"""
            from core.rl_env import evaluate_agent

            def get_action(obs):
                obs_tensor = torch.FloatTensor(obs).unsqueeze(0).to(self.hp.device)
                with torch.no_grad():
                    logits, _ = self.model(obs_tensor)
                    return torch.argmax(logits, dim=-1).item()

            metrics = evaluate_agent(env, get_action, n_episodes)
            return {
                "sharpe": metrics["sharpe_ratio"],
                "return_pct": metrics["total_return_pct"],
                "max_dd_pct": metrics["max_drawdown_pct"],
                "final_equity": metrics["final_equity"],
                "n_trades": metrics["n_trades"]
            }

        def save(self, path: str):
            """保存模型"""
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            torch.save({
                "model_state": self.model.state_dict(),
                "optimizer_state": self.optimizer.state_dict(),
                "obs_dim": self.obs_dim,
                "n_actions": self.n_actions,
                "train_steps": self.train_steps,
                "episode_rewards": self.episode_rewards,
                "loss_history": self.loss_history,
                "hyperparams": self.hp
            }, path)
            logger.info(f"[PPO] Model saved: {path}")

        def load(self, path: str):
            """加载模型"""
            checkpoint = torch.load(path, map_location=self.hp.device, weights_only=False)
            self.model.load_state_dict(checkpoint["model_state"])
            self.optimizer.load_state_dict(checkpoint["optimizer_state"])
            self.train_steps = checkpoint.get("train_steps", 0)
            self.episode_rewards = checkpoint.get("episode_rewards", [])
            self.loss_history = checkpoint.get("loss_history", [])
            logger.info(f"[PPO] Model loaded: {path} (step {self.train_steps})")


# ==================== NumPy回退实现 ====================

class NumPyPPOAgent:
    """
    轻量级NumPy PPO Agent (无PyTorch依赖)
    
    使用两层全连接网络 + 梯度下降手动实现。
    适用于快速原型和小数据集场景。
    """

    def __init__(self, obs_dim: int, n_actions: int, 
                 hidden_dim: int = 64, lr: float = 1e-3):
        self.obs_dim = obs_dim
        self.n_actions = n_actions
        self.lr = lr

        # 网络权重
        scale1 = np.sqrt(2.0 / obs_dim)
        self.W1 = np.random.randn(obs_dim, hidden_dim).astype(np.float32) * scale1
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)
        self.W2 = np.random.randn(hidden_dim, n_actions).astype(np.float32) * 0.01
        self.b2 = np.zeros(n_actions, dtype=np.float32)

        # Critic head
        self.Wv = np.random.randn(hidden_dim, 1).astype(np.float32) * 0.01
        self.bv = np.zeros(1, dtype=np.float32)

        self.train_steps = 0
        logger.info(f"[RL-NumPy] Agent initialized: obs_dim={obs_dim}, hidden={hidden_dim}")

    def _forward_actor(self, obs: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Actor前向: obs → logits"""
        x = obs @ self.W1 + self.b1
        x = np.maximum(x, 0)  # ReLU
        logits = x @ self.W2 + self.b2
        probs = self._softmax(logits)
        return logits, probs

    def _forward_critic(self, obs: np.ndarray) -> float:
        """Critic前向: obs → value"""
        x = obs @ self.W1 + self.b1
        x = np.maximum(x, 0)
        return (x @ self.Wv + self.bv)[0]

    def _softmax(self, x):
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()

    def get_action(self, obs: np.ndarray, deterministic: bool = False):
        _, probs = self._forward_actor(obs)
        value = self._forward_critic(obs)

        if deterministic:
            action = np.argmax(probs)
        else:
            action = np.random.choice(self.n_actions, p=probs)

        log_prob = np.log(probs[action] + 1e-8)
        return action, log_prob, value

    def train_step(self, obs_batch, actions_batch, advantages_batch, 
                   returns_batch, old_log_probs_batch, clip_epsilon=0.2):
        """单步训练"""
        n = len(obs_batch)
        total_loss = 0.0

        for i in range(n):
            obs = obs_batch[i]
            action = actions_batch[i]
            advantage = advantages_batch[i]
            ret = returns_batch[i]
            old_lp = old_log_probs_batch[i]

            # Forward
            logits, probs = self._forward_actor(obs)
            value = self._forward_critic(obs)

            # Actor loss (PPO clip)
            new_lp = np.log(probs[action] + 1e-8)
            ratio = np.exp(new_lp - old_lp)
            surr1 = ratio * advantage
            surr2 = np.clip(ratio, 1 - clip_epsilon, 1 + clip_epsilon) * advantage
            policy_loss = -min(surr1, surr2)

            # Critic loss
            value_loss = (value - ret) ** 2

            loss = policy_loss + 0.5 * value_loss
            total_loss += loss

            # Backward (manual gradient)
            # 这里简化处理，实际使用数值梯度
            epsilon = 1e-5
            grad_W2 = np.zeros_like(self.W2)
            grad_b2 = np.zeros_like(self.b2)
            grad_Wv = np.zeros_like(self.Wv)
            grad_bv = np.zeros_like(self.bv)

            for j in range(self.n_actions):
                old_val = self.W2[:, j].copy()
                self.W2[:, j] += epsilon
                _, new_probs = self._forward_actor(obs)
                new_lp_j = np.log(new_probs[action] + 1e-8)
                new_ratio = np.exp(new_lp_j - old_lp)
                new_surr = -min(new_ratio * advantage, 
                               np.clip(new_ratio, 1 - clip_epsilon, 1 + clip_epsilon) * advantage)
                grad = (new_surr - policy_loss) / epsilon
                self.W2[:, j] = old_val
                grad_W2[:, j] = grad

                old_b2_j = self.b2[j]
                self.b2[j] += epsilon
                _, new_probs2 = self._forward_actor(obs)
                new_lp_b = np.log(new_probs2[action] + 1e-8)
                new_ratio_b = np.exp(new_lp_b - old_lp)
                new_surr_b = -min(new_ratio_b * advantage,
                                 np.clip(new_ratio_b, 1 - clip_epsilon, 1 + clip_epsilon) * advantage)
                self.b2[j] = old_b2_j
                grad_b2[j] = (new_surr_b - policy_loss) / epsilon

            for j in range(1):
                old_wv = self.Wv[:, j].copy()
                self.Wv[:, j] += epsilon
                new_val = self._forward_critic(obs)
                new_val_loss = (new_val - ret) ** 2
                grad_Wv[:, j] = (new_val_loss - value_loss) / epsilon
                self.Wv[:, j] = old_wv

                old_bv = self.bv[j]
                self.bv[j] += epsilon
                new_val2 = self._forward_critic(obs)
                new_val_loss2 = (new_val2 - ret) ** 2
                grad_bv[j] = (new_val_loss2 - value_loss) / epsilon
                self.bv[j] = old_bv

            # 更新权重
            self.W2 -= self.lr * grad_W2
            self.b2 -= self.lr * grad_b2
            self.Wv -= self.lr * grad_Wv
            self.bv -= self.lr * grad_bv

            self.train_steps += 1

        return total_loss / n


# ==================== 工厂函数 ====================

def create_ppo_trainer(obs_dim: int, n_actions: int = 3,
                       use_torch: bool = True,
                       hidden_dim: int = 128,
                       lr: float = 3e-4):
    """创建PPO训练器（自动选择实现）"""
    if use_torch and TORCH_AVAILABLE:
        hp = PPOHyperparams(learning_rate=lr, hidden_dim=hidden_dim)
        return PPOTrainer(obs_dim, n_actions, hp)
    else:
        return NumPyPPOAgent(obs_dim, n_actions, hidden_dim=hidden_dim, lr=lr)
