"""重排序模块。

使用 Cross-Encoder 模型对候选结果进行精细排序，
提升最终检索质量。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RerankConfig:
    """重排序配置。"""

    model_name: str = "BAAI/bge-reranker-base"  # 中文优化的重排序模型
    max_length: int = 512  # 最大序列长度
    batch_size: int = 32  # 批处理大小


class CrossEncoderReranker:
    """Cross-Encoder 重排序器。"""

    def __init__(self, config: Optional[RerankConfig] = None):
        """初始化重排序器。

        Args:
            config: 重排序配置
        """
        self.config = config or RerankConfig()
        self.model = None
        self._initialized = False

    def _ensure_loaded(self) -> None:
        """懒加载模型。"""
        if self._initialized:
            return

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise ImportError(
                "请安装 sentence-transformers: pip install sentence-transformers"
            )

        print(f"正在加载重排序模型：{self.config.model_name}")
        self.model = CrossEncoder(
            self.config.model_name, max_length=self.config.max_length
        )
        self._initialized = True

    def rerank(
        self,
        query: str,
        candidates: list[tuple[int, str]],
        top_k: Optional[int] = None,
    ) -> list[tuple[int, float]]:
        """对候选结果进行重排序。

        Args:
            query: 查询文本
            candidates: 候选列表 [(chunk_id, content), ...]
            top_k: 返回结果数量（None 则返回全部）

        Returns:
            [(chunk_id, rerank_score), ...] 按分数降序排列
        """
        self._ensure_loaded()

        if not candidates:
            return []

        # 准备输入对
        pairs = [[query, content] for _, content in candidates]

        # 批量预测
        scores = self.model.predict(
            pairs, batch_size=self.config.batch_size, show_progress_bar=False
        )

        # 关联回 chunk_id
        scored_results = [
            (chunk_id, float(score)) for (chunk_id, _), score in zip(candidates, scores)
        ]

        # 按分数降序排序
        scored_results.sort(key=lambda x: x[1], reverse=True)

        # 截取 top-k
        if top_k is not None:
            scored_results = scored_results[:top_k]

        return scored_results


class HybridReranker:
    """混合重排序器。

    支持多种策略：
    1. Reciprocal Rank Fusion (RRF)
    2. Linear Combination
    3. Cross-Encoder
    """

    def __init__(
        self,
        cross_encoder_config: Optional[RerankConfig] = None,
        use_cross_encoder: bool = True,
    ):
        """初始化混合重排序器。

        Args:
            cross_encoder_config: Cross-Encoder 配置
            use_cross_encoder: 是否启用 Cross-Encoder（否则仅使用 RRF）
        """
        self.use_cross_encoder = use_cross_encoder
        if use_cross_encoder:
            self.cross_encoder = CrossEncoderReranker(cross_encoder_config)
        else:
            self.cross_encoder = None

    def rrf_fusion(
        self,
        ranked_lists: list[list[tuple[int, float]]],
        k: int = 60,
    ) -> list[tuple[int, float]]:
        """Reciprocal Rank Fusion 融合多个排序结果。

        Args:
            ranked_lists: 多个排序结果列表
            k: RRF 平滑参数

        Returns:
            融合后的排序结果
        """
        from collections import defaultdict

        rrf_scores = defaultdict(float)

        for ranked_list in ranked_lists:
            for rank, (chunk_id, _) in enumerate(ranked_list, start=1):
                rrf_scores[chunk_id] += 1.0 / (k + rank)

        # 排序
        fused_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        return fused_results

    def linear_combination(
        self,
        scores_dict: dict[int, dict[str, float]],
        weights: dict[str, float],
    ) -> list[tuple[int, float]]:
        """线性组合多个分数。

        Args:
            scores_dict: {chunk_id: {'bm25': 0.5, 'vector': 0.8, ...}}
            weights: 各分数来源的权重 {'bm25': 0.3, 'vector': 0.7}

        Returns:
            组合后的排序结果
        """
        combined_scores = {}

        for chunk_id, scores in scores_dict.items():
            total = sum(scores.get(source, 0.0) * weight for source, weight in weights.items())
            combined_scores[chunk_id] = total

        sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results

    def rerank_with_cross_encoder(
        self,
        query: str,
        candidates: list[tuple[int, str]],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """使用 Cross-Encoder 进行重排序。

        Args:
            query: 查询文本
            candidates: 候选列表 [(chunk_id, content), ...]
            top_k: 返回结果数量

        Returns:
            重排序后的结果
        """
        if not self.use_cross_encoder or self.cross_encoder is None:
            # 降级为恒等排序
            return [(cid, 1.0 / (idx + 1)) for idx, (cid, _) in enumerate(candidates)][
                :top_k
            ]

        return self.cross_encoder.rerank(query, candidates, top_k=top_k)
