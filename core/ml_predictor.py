#!/usr/bin/env python3
"""
科学智能交易系统 - 机器学习预测模型模块
基于历史市场数据训练模型，预测市场趋势和交易信号
"""

import json
import time
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import threading
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
from sklearn.exceptions import ConvergenceWarning
import joblib

from core.logger import logger
from core.datastore import get_datastore
from core.market_data_analyzer import get_market_data_analyzer, MarketPrice, TechnicalIndicators


warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=UserWarning)


class ModelType(Enum):
    """机器学习模型类型"""
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    LOGISTIC_REGRESSION = "logistic_regression"
    SVM = "svm"
    NEURAL_NETWORK = "neural_network"
    ENSEMBLE = "ensemble"


class PredictionHorizon(Enum):
    """预测时间范围"""
    SHORT_TERM = "short_term"    # 1-5根K线
    MEDIUM_TERM = "medium_term"  # 5-20根K线
    LONG_TERM = "long_term"      # 20-100根K线


@dataclass
class ModelConfig:
    """模型配置"""
    model_type: ModelType = ModelType.RANDOM_FOREST
    prediction_horizon: PredictionHorizon = PredictionHorizon.SHORT_TERM
    lookback_period: int = 100  # 回看周期（K线数量）
    feature_window: int = 20    # 特征窗口大小
    retrain_interval: int = 86400  # 重训练间隔（秒）
    min_confidence: float = 0.65   # 最小置信度阈值
    
    # 模型超参数
    n_estimators: int = 100
    max_depth: int = 10
    learning_rate: float = 0.1
    random_state: int = 42


@dataclass
class FeatureSet:
    """特征集合"""
    technical_features: List[float]      # 技术指标特征
    price_features: List[float]          # 价格特征
    volume_features: List[float]         # 成交量特征
    volatility_features: List[float]     # 波动率特征
    pattern_features: List[float]        # 价格形态特征
    time_features: List[float]           # 时间特征
    
    def to_array(self) -> np.ndarray:
        """转换为特征数组"""
        return np.concatenate([
            self.technical_features,
            self.price_features,
            self.volume_features,
            self.volatility_features,
            self.pattern_features,
            self.time_features
        ])
    
    @property
    def size(self) -> int:
        """特征维度"""
        return len(self.technical_features) + len(self.price_features) + \
               len(self.volume_features) + len(self.volatility_features) + \
               len(self.pattern_features) + len(self.time_features)


@dataclass
class ModelPrediction:
    """模型预测结果"""
    symbol: str
    timeframe: str
    timestamp: float
    prediction: str  # "BUY", "SELL", "HOLD"
    confidence: float
    probabilities: Dict[str, float]  # 各类别概率
    horizon: PredictionHorizon
    features_used: int
    model_type: ModelType
    metadata: Dict[str, Any]


class MLPredictor:
    """机器学习预测器"""
    
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.datastore = get_datastore()
        self.market_analyzer = get_market_data_analyzer()
        
        # 模型相关
        self.models: Dict[str, Any] = {}  # 模型缓存 key: symbol_timeframe_horizon_modeltype
        self.scalers: Dict[str, StandardScaler] = {}  # 特征标准化器
        self.model_metadata: Dict[str, Dict] = {}  # 模型元数据
        
        # 训练数据缓存
        self.training_data: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        
        # 运行状态
        self.running = False
        self.training_thread: Optional[threading.Thread] = None
        
        # 模型存储路径
        self.model_dir = Path("models")
        self.model_dir.mkdir(exist_ok=True)
        
        logger.info(f"[AI] 机器学习预测器初始化完成，模型类型: {self.config.model_type.value}")
    
    def start(self):
        """启动预测器"""
        if self.running:
            logger.warning("[WARN]  预测器已在运行中")
            return
        
        self.running = True
        self.training_thread = threading.Thread(target=self._training_loop, daemon=True)
        self.training_thread.start()
        logger.info("-> 机器学习预测器已启动")
    
    def stop(self):
        """停止预测器"""
        self.running = False
        if self.training_thread:
            self.training_thread.join(timeout=10)
        logger.info("🛑 机器学习预测器已停止")
    
    def _training_loop(self):
        """模型训练循环"""
        logger.info("[REFRESH] 模型训练循环开始")
        
        last_training_time = {}
        
        while self.running:
            try:
                # 获取需要训练的品种
                symbols = ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "XAUUSD"]
                timeframes = ["M5", "M15", "H1"]
                horizons = [PredictionHorizon.SHORT_TERM, PredictionHorizon.MEDIUM_TERM]
                
                for symbol in symbols:
                    for timeframe in timeframes:
                        for horizon in horizons:
                            model_key = self._get_model_key(symbol, timeframe, horizon)
                            
                            # 检查是否需要重训练
                            last_time = last_training_time.get(model_key, 0)
                            current_time = time.time()
                            
                            if current_time - last_time > self.config.retrain_interval:
                                logger.info(f"[REFRESH] 开始训练模型: {symbol}_{timeframe}_{horizon.value}")
                                
                                try:
                                    success = self.train_model(symbol, timeframe, horizon)
                                    if success:
                                        last_training_time[model_key] = current_time
                                        logger.info(f"[OK] 模型训练完成: {symbol}_{timeframe}_{horizon.value}")
                                    else:
                                        logger.warning(f"[WARN]  模型训练失败: {symbol}_{timeframe}_{horizon.value}")
                                except Exception as e:
                                    logger.error(f"[ERR] 模型训练异常: {e}")
                
                time.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"[ERR] 训练循环异常: {e}")
                time.sleep(30)
    
    def _get_model_key(self, symbol: str, timeframe: str, horizon: PredictionHorizon) -> str:
        """生成模型缓存键"""
        return f"{symbol}_{timeframe}_{horizon.value}_{self.config.model_type.value}"
    
    def load_model(self, symbol: str, timeframe: str, horizon: PredictionHorizon) -> bool:
        """加载已训练的模型"""
        model_key = self._get_model_key(symbol, timeframe, horizon)
        
        # 检查内存中是否已有模型
        if model_key in self.models:
            return True
        
        # 尝试从磁盘加载
        model_path = self.model_dir / f"{model_key}.joblib"
        scaler_path = self.model_dir / f"{model_key}_scaler.joblib"
        metadata_path = self.model_dir / f"{model_key}_metadata.json"
        
        try:
            if model_path.exists() and scaler_path.exists():
                self.models[model_key] = joblib.load(model_path)
                self.scalers[model_key] = joblib.load(scaler_path)
                
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        self.model_metadata[model_key] = json.load(f)
                
                logger.info(f"📂 模型加载成功: {model_key}")
                return True
            else:
                logger.debug(f"📂 模型文件不存在: {model_key}")
                return False
                
        except Exception as e:
            logger.error(f"[ERR] 加载模型失败: {e}")
            return False
    
    def save_model(self, symbol: str, timeframe: str, horizon: PredictionHorizon):
        """保存模型到磁盘"""
        model_key = self._get_model_key(symbol, timeframe, horizon)
        
        if model_key not in self.models or model_key not in self.scalers:
            logger.warning(f"[WARN]  无法保存未训练的模型: {model_key}")
            return
        
        try:
            model_path = self.model_dir / f"{model_key}.joblib"
            scaler_path = self.model_dir / f"{model_key}_scaler.joblib"
            metadata_path = self.model_dir / f"{model_key}_metadata.json"
            
            joblib.dump(self.models[model_key], model_path)
            joblib.dump(self.scalers[model_key], scaler_path)
            
            if model_key in self.model_metadata:
                with open(metadata_path, 'w') as f:
                    json.dump(self.model_metadata[model_key], f, indent=2)
            
            logger.debug(f"💾 模型保存成功: {model_key}")
            
        except Exception as e:
            logger.error(f"[ERR] 保存模型失败: {e}")
    
    def prepare_training_data(self, symbol: str, timeframe: str, horizon: PredictionHorizon) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """准备训练数据"""
        try:
            # 获取历史数据
            # 这里简化实现，实际应从数据库获取大量历史数据
            # 目前使用模拟数据
            
            # 模拟生成训练数据
            n_samples = 1000
            n_features = 50
            
            # 生成特征
            X = np.random.randn(n_samples, n_features)
            
            # 生成标签（模拟市场趋势）
            # 假设特征0是价格趋势，特征1是成交量，特征2是波动率
            trend_signal = np.sign(X[:, 0] + 0.5 * X[:, 1] - 0.3 * X[:, 2])
            y = np.where(trend_signal > 0, 1, 0)  # 1: BUY, 0: SELL
            
            # 添加一些HOLD样本（噪音）
            noise_indices = np.random.choice(n_samples, size=n_samples//10, replace=False)
            y[noise_indices] = 2  # 2: HOLD
            
            logger.debug(f"[DATA] 训练数据准备完成: {symbol}_{timeframe}, 样本数: {n_samples}, 特征数: {n_features}")
            return X, y
            
        except Exception as e:
            logger.error(f"[ERR] 准备训练数据失败: {e}")
            return None
    
    def extract_features(self, prices: List[MarketPrice], indicators: List[TechnicalIndicators]) -> FeatureSet:
        """从市场数据中提取特征"""
        try:
            if len(prices) < 20 or len(indicators) < 20:
                raise ValueError("数据不足，需要至少20个数据点")
            
            # 提取最近的数据
            recent_prices = prices[-20:]
            recent_indicators = indicators[-20:] if indicators else []
            
            # 技术指标特征
            technical_features = []
            if recent_indicators:
                latest = recent_indicators[-1]
                tech_feat = [
                    latest.ma5 or 0, latest.ma10 or 0, latest.ma20 or 0,
                    latest.ma50 or 0, latest.ma100 or 0, latest.ma200 or 0,
                    latest.rsi or 0, latest.macd or 0, latest.macd_signal or 0,
                    latest.macd_hist or 0, latest.stoch_k or 0, latest.stoch_d or 0,
                    latest.cci or 0, latest.adx or 0, latest.atr or 0,
                    latest.bollinger_upper or 0, latest.bollinger_middle or 0,
                    latest.bollinger_lower or 0, latest.obv or 0, latest.volume_ratio or 0
                ]
                technical_features = [float(f) for f in tech_feat]
            else:
                technical_features = [0.0] * 20
            
            # 价格特征
            price_values = [p.close for p in recent_prices]
            price_features = []
            if len(price_values) >= 2:
                # 价格变化率
                returns = np.diff(price_values) / price_values[:-1]
                price_features.extend([
                    float(np.mean(price_values)),  # 平均价格
                    float(np.std(price_values)),   # 价格标准差
                    float(np.min(price_values)),   # 最低价
                    float(np.max(price_values)),   # 最高价
                    float(price_values[-1]),       # 当前价格
                    float(returns[-1] if len(returns) > 0 else 0),  # 最新收益率
                    float(np.mean(returns) if len(returns) > 0 else 0),  # 平均收益率
                    float(np.std(returns) if len(returns) > 0 else 0),   # 收益率波动率
                ])
            else:
                price_features = [0.0] * 8
            
            # 成交量特征
            volume_values = [p.volume or 0 for p in recent_prices]
            volume_features = []
            if len(volume_values) > 0:
                volume_features.extend([
                    float(np.mean(volume_values)),  # 平均成交量
                    float(np.std(volume_values)),   # 成交量标准差
                    float(volume_values[-1]),       # 当前成交量
                    float(volume_values[-1] / np.mean(volume_values) if np.mean(volume_values) > 0 else 1.0),  # 成交量比率
                ])
            else:
                volume_features = [0.0] * 4
            
            # 波动率特征
            if len(price_values) >= 10:
                # 滚动波动率
                rolling_std = []
                for i in range(len(price_values) - 9):
                    window = price_values[i:i+10]
                    rolling_std.append(np.std(window))
                
                volatility_features = [
                    float(np.mean(rolling_std) if rolling_std else 0),  # 平均波动率
                    float(np.std(rolling_std) if rolling_std else 0),   # 波动率变化
                    float(rolling_std[-1] if rolling_std else 0),       # 当前波动率
                ]
            else:
                volatility_features = [0.0] * 3
            
            # 价格形态特征（简化）
            pattern_features = []
            if len(price_values) >= 5:
                # 简单形态识别
                recent_prices = price_values[-5:]
                pattern_features = [
                    float(1 if recent_prices[-1] > recent_prices[-2] else 0),  # 上涨
                    float(1 if recent_prices[-1] < recent_prices[-2] else 0),  # 下跌
                    float(1 if recent_prices[-1] > np.mean(recent_prices) else 0),  # 高于平均
                    float(1 if recent_prices[-1] < np.mean(recent_prices) else 0),  # 低于平均
                ]
            else:
                pattern_features = [0.0] * 4
            
            # 时间特征
            current_time = datetime.now()
            time_features = [
                float(current_time.hour / 24.0),  # 小时（归一化）
                float(current_time.minute / 60.0),  # 分钟
                float(current_time.weekday() / 7.0),  # 星期
                float(1 if 9 <= current_time.hour < 17 else 0),  # 交易时段
            ]
            
            return FeatureSet(
                technical_features=technical_features,
                price_features=price_features,
                volume_features=volume_features,
                volatility_features=volatility_features,
                pattern_features=pattern_features,
                time_features=time_features
            )
            
        except Exception as e:
            logger.error(f"[ERR] 特征提取失败: {e}")
            # 返回空特征
            return FeatureSet(
                technical_features=[0.0] * 20,
                price_features=[0.0] * 8,
                volume_features=[0.0] * 4,
                volatility_features=[0.0] * 3,
                pattern_features=[0.0] * 4,
                time_features=[0.0] * 4
            )
    
    def create_model(self) -> Any:
        """创建机器学习模型"""
        model_type = self.config.model_type
        
        if model_type == ModelType.RANDOM_FOREST:
            return RandomForestClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                random_state=self.config.random_state,
                n_jobs=-1
            )
        elif model_type == ModelType.GRADIENT_BOOSTING:
            return GradientBoostingClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                random_state=self.config.random_state
            )
        elif model_type == ModelType.LOGISTIC_REGRESSION:
            return LogisticRegression(
                max_iter=1000,
                random_state=self.config.random_state,
                solver='lbfgs'
            )
        elif model_type == ModelType.SVM:
            return SVC(
                kernel='rbf',
                probability=True,
                random_state=self.config.random_state
            )
        elif model_type == ModelType.NEURAL_NETWORK:
            return MLPClassifier(
                hidden_layer_sizes=(100, 50),
                max_iter=1000,
                random_state=self.config.random_state,
                learning_rate='adaptive'
            )
        else:
            # 默认使用随机森林
            return RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=self.config.random_state,
                n_jobs=-1
            )
    
    def train_model(self, symbol: str, timeframe: str, horizon: PredictionHorizon) -> bool:
        """训练机器学习模型"""
        try:
            model_key = self._get_model_key(symbol, timeframe, horizon)
            
            # 准备训练数据
            data = self.prepare_training_data(symbol, timeframe, horizon)
            if data is None:
                logger.warning(f"[WARN]  无法获取训练数据: {symbol}_{timeframe}")
                return False
            
            X, y = data
            
            # 划分训练集和测试集
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=self.config.random_state, stratify=y
            )
            
            # 特征标准化
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # 创建并训练模型
            model = self.create_model()
            
            logger.info(f"🏋️  开始训练模型: {model_key}, 训练样本: {X_train.shape[0]}")
            
            model.fit(X_train_scaled, y_train)
            
            # 评估模型
            y_pred = model.predict(X_test_scaled)
            y_pred_proba = model.predict_proba(X_test_scaled)
            
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
            recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
            f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
            
            # 保存模型和元数据
            self.models[model_key] = model
            self.scalers[model_key] = scaler
            self.model_metadata[model_key] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "horizon": horizon.value,
                "model_type": model_type.value,
                "accuracy": float(accuracy),
                "precision": float(precision),
                "recall": float(recall),
                "f1_score": float(f1),
                "training_samples": int(X_train.shape[0]),
                "test_samples": int(X_test.shape[0]),
                "feature_count": int(X.shape[1]),
                "last_trained": datetime.now().isoformat(),
                "config": {
                    "n_estimators": self.config.n_estimators,
                    "max_depth": self.config.max_depth,
                    "learning_rate": self.config.learning_rate,
                    "random_state": self.config.random_state
                }
            }
            
            # 保存到磁盘
            self.save_model(symbol, timeframe, horizon)
            
            logger.info(f"[OK] 模型训练完成: {model_key}")
            logger.info(f"  准确率: {accuracy:.4f}, F1分数: {f1:.4f}")
            logger.info(f"  训练样本: {X_train.shape[0]}, 测试样本: {X_test.shape[0]}")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERR] 模型训练失败: {e}")
            return False
    
    def predict(self, symbol: str, timeframe: str, horizon: PredictionHorizon) -> Optional[ModelPrediction]:
        """使用模型进行预测"""
        try:
            model_key = self._get_model_key(symbol, timeframe, horizon)
            
            # 加载模型（如果尚未加载）
            if not self.load_model(symbol, timeframe, horizon):
                logger.warning(f"[WARN]  模型未训练: {model_key}")
                return None
            
            # 获取市场数据（简化实现，实际应从数据库获取）
            # 这里使用模拟数据
            feature_set = self.extract_features([], [])
            
            # 特征标准化
            features = feature_set.to_array().reshape(1, -1)
            features_scaled = self.scalers[model_key].transform(features)
            
            # 预测
            model = self.models[model_key]
            prediction = model.predict(features_scaled)[0]
            probabilities = model.predict_proba(features_scaled)[0]
            
            # 将数字标签转换为交易动作
            # 0: SELL, 1: BUY, 2: HOLD
            label_map = {0: "SELL", 1: "BUY", 2: "HOLD"}
            prediction_label = label_map.get(int(prediction), "HOLD")
            
            # 获取置信度（预测类别的概率）
            confidence = float(probabilities[prediction])
            
            # 如果置信度低于阈值，则返回HOLD
            if confidence < self.config.min_confidence:
                prediction_label = "HOLD"
                confidence = 0.5
            
            # 构建概率字典
            prob_dict = {}
            for i, prob in enumerate(probabilities):
                label = label_map.get(i, f"CLASS_{i}")
                prob_dict[label] = float(prob)
            
            result = ModelPrediction(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=time.time(),
                prediction=prediction_label,
                confidence=confidence,
                probabilities=prob_dict,
                horizon=horizon,
                features_used=feature_set.size,
                model_type=self.config.model_type,
                metadata={
                    "model_key": model_key,
                    "model_accuracy": self.model_metadata.get(model_key, {}).get("accuracy", 0),
                    "prediction_time": datetime.now().isoformat()
                }
            )
            
            logger.debug(f"🔮 模型预测: {symbol} {timeframe} -> {prediction_label} ({confidence:.2f})")
            return result
            
        except Exception as e:
            logger.error(f"[ERR] 模型预测失败: {e}")
            return None
    
    def predict_with_market_data(self, symbol: str, timeframe: str, 
                                prices: List[MarketPrice], 
                                indicators: List[TechnicalIndicators]) -> Optional[ModelPrediction]:
        """使用实际市场数据进行预测"""
        try:
            # 提取特征
            feature_set = self.extract_features(prices, indicators)
            
            # 使用短期预测
            horizon = PredictionHorizon.SHORT_TERM
            
            model_key = self._get_model_key(symbol, timeframe, horizon)
            
            # 加载模型
            if not self.load_model(symbol, timeframe, horizon):
                logger.warning(f"[WARN]  模型未训练: {model_key}")
                return None
            
            # 特征标准化
            features = feature_set.to_array().reshape(1, -1)
            features_scaled = self.scalers[model_key].transform(features)
            
            # 预测
            model = self.models[model_key]
            prediction = model.predict(features_scaled)[0]
            probabilities = model.predict_proba(features_scaled)[0]
            
            # 标签映射
            label_map = {0: "SELL", 1: "BUY", 2: "HOLD"}
            prediction_label = label_map.get(int(prediction), "HOLD")
            
            # 置信度处理
            confidence = float(probabilities[prediction])
            if confidence < self.config.min_confidence:
                prediction_label = "HOLD"
                confidence = 0.5
            
            # 概率字典
            prob_dict = {}
            for i, prob in enumerate(probabilities):
                label = label_map.get(i, f"CLASS_{i}")
                prob_dict[label] = float(prob)
            
            result = ModelPrediction(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=time.time(),
                prediction=prediction_label,
                confidence=confidence,
                probabilities=prob_dict,
                horizon=horizon,
                features_used=feature_set.size,
                model_type=self.config.model_type,
                metadata={
                    "model_key": model_key,
                    "model_accuracy": self.model_metadata.get(model_key, {}).get("accuracy", 0),
                    "prediction_time": datetime.now().isoformat(),
                    "feature_summary": {
                        "technical": len(feature_set.technical_features),
                        "price": len(feature_set.price_features),
                        "volume": len(feature_set.volume_features),
                        "volatility": len(feature_set.volatility_features),
                        "pattern": len(feature_set.pattern_features),
                        "time": len(feature_set.time_features)
                    }
                }
            )
            
            logger.info(f"🔮 市场数据预测: {symbol} {timeframe} -> {prediction_label} (置信度: {confidence:.2f})")
            return result
            
        except Exception as e:
            logger.error(f"[ERR] 市场数据预测失败: {e}")
            return None
    
    def get_model_info(self, symbol: str, timeframe: str, horizon: PredictionHorizon) -> Optional[Dict[str, Any]]:
        """获取模型信息"""
        model_key = self._get_model_key(symbol, timeframe, horizon)
        
        if model_key in self.model_metadata:
            return self.model_metadata[model_key]
        
        # 尝试从磁盘加载元数据
        metadata_path = self.model_dir / f"{model_key}_metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                self.model_metadata[model_key] = metadata
                return metadata
            except:
                pass
        
        return None
    
    def get_all_models_info(self) -> List[Dict[str, Any]]:
        """获取所有模型信息"""
        models_info = []
        
        # 检查模型目录
        for metadata_file in self.model_dir.glob("*_metadata.json"):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                models_info.append(metadata)
            except:
                pass
        
        # 添加内存中的模型
        for model_key, metadata in self.model_metadata.items():
            if not any(m.get("model_key") == model_key for m in models_info):
                models_info.append(metadata)
        
        return models_info


# 全局预测器实例
_global_predictor: Optional[MLPredictor] = None


def get_ml_predictor() -> MLPredictor:
    """获取全局机器学习预测器实例"""
    global _global_predictor
    if not _global_predictor:
        _global_predictor = MLPredictor()
    return _global_predictor


if __name__ == "__main__":
    # 测试机器学习预测器
    print("="*70)
    print("[TOOL] 测试机器学习预测系统")
    print("="*70)
    
    predictor = MLPredictor()
    
    # 启动预测器
    predictor.start()
    
    # 等待模型训练
    print("\n🏋️  等待模型训练...")
    time.sleep(5)
    
    # 进行预测
    print("\n🔮 进行预测...")
    prediction = predictor.predict("EURUSD", "M5", PredictionHorizon.SHORT_TERM)
    
    if prediction:
        print(f"[OK] 预测结果: {prediction.prediction}")
        print(f"   置信度: {prediction.confidence:.2f}")
        print(f"   概率分布: {prediction.probabilities}")
        print(f"   使用特征数: {prediction.features_used}")
        print(f"   模型类型: {prediction.model_type.value}")
    else:
        print("[ERR] 预测失败")
    
    # 获取模型信息
    print("\n[DATA] 模型信息:")
    models_info = predictor.get_all_models_info()
    for info in models_info[:3]:  # 显示前3个模型
        print(f"  - {info.get('symbol', 'unknown')}_{info.get('timeframe', 'unknown')}: "
              f"准确率={info.get('accuracy', 0):.2f}, 样本数={info.get('training_samples', 0)}")
    
    # 停止预测器
    predictor.stop()
    
    print("\n[OK] 机器学习预测器测试完成！")