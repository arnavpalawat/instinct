"""Deduplicator: removes near-duplicate articles using TF-IDF cosine similarity."""

import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.models.article import Article

logger = logging.getLogger(__name__)

# Source authority ranking: higher is more authoritative.
SOURCE_AUTHORITY: dict[str, int] = {
    "sec_edgar": 4,
    "pr_newswire": 3,
    "businesswire": 3,
    "finnhub": 2,
    "google_news": 1,
}


class Deduplicator:
    """Remove near-duplicate articles using TF-IDF cosine similarity.

    When duplicates are found, the best article is kept based on:
        1. Higher relevance score
        2. More authoritative source (SEC > PR feeds > news)
        3. Earlier publication time
    Tickers and sectors from duplicate articles are merged into the kept article.
    """

    def __init__(self, similarity_threshold: float = 0.7):
        if not 0.0 < similarity_threshold <= 1.0:
            raise ValueError(
                f"similarity_threshold must be in (0, 1], got {similarity_threshold}"
            )
        self.threshold = similarity_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deduplicate(self, articles: list[Article]) -> list[Article]:
        """Return a deduplicated list of articles.

        Articles whose TF-IDF cosine similarity exceeds *self.threshold* are
        grouped together.  From each group the single best article is kept and
        the tickers / sectors of the other members are merged into it.
        """
        if len(articles) <= 1:
            return list(articles)

        texts = [self._article_text(a) for a in articles]

        # Guard against all-empty texts (TfidfVectorizer would raise).
        if all(t.strip() == "" for t in texts):
            return list(articles)

        try:
            vectorizer = TfidfVectorizer(
                stop_words="english", max_features=5000
            )
            tfidf_matrix = vectorizer.fit_transform(texts)
        except ValueError:
            # Can happen if every document is empty after stop-word removal.
            logger.warning("TF-IDF vectorisation failed; returning articles unchanged.")
            return list(articles)

        sim_matrix = cosine_similarity(tfidf_matrix)

        clusters = self._build_clusters(sim_matrix, len(articles))
        kept: list[Article] = []

        for cluster_indices in clusters:
            cluster_articles = [articles[i] for i in cluster_indices]
            best = self._pick_best(cluster_articles)
            if len(cluster_articles) > 1:
                self._merge_metadata(best, cluster_articles)
                logger.debug(
                    "Merged %d duplicates into '%s'",
                    len(cluster_articles) - 1,
                    best.title,
                )
            kept.append(best)

        logger.info(
            "Deduplication: %d -> %d articles (removed %d duplicates)",
            len(articles),
            len(kept),
            len(articles) - len(kept),
        )
        return kept

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _article_text(article: Article) -> str:
        """Combine title, summary, and raw content for richer vectorisation."""
        parts = [article.title, article.summary]
        if article.raw_content:
            parts.append(article.raw_content[:1000])
        return " ".join(parts)

    def _build_clusters(
        self, sim_matrix, n: int
    ) -> list[list[int]]:
        """Union-find clustering of articles that exceed the similarity threshold.

        Returns a list of clusters, each cluster being a list of article
        indices.  Articles that are not similar to any other form singleton
        clusters.
        """
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= self.threshold:
                    union(i, j)

        # Group indices by their root.
        groups: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        return list(groups.values())

    @staticmethod
    def _pick_best(cluster: list[Article]) -> Article:
        """Select the single best article from a cluster of duplicates.

        Sorting key (descending priority):
            1. Higher relevance_score
            2. Higher source authority
            3. Earlier publication time
        """
        def sort_key(article: Article) -> tuple:
            authority = SOURCE_AUTHORITY.get(article.source, 0)
            # For publication time, earlier is better so we negate the
            # timestamp.  Articles without a publication date sort last.
            if article.published is not None:
                pub_key = -article.published.timestamp()
            else:
                pub_key = 0  # treat missing as epoch -> sorts after real dates with negative ts
            return (article.relevance_score, authority, pub_key)

        return max(cluster, key=sort_key)

    @staticmethod
    def _merge_metadata(best: Article, cluster: list[Article]) -> None:
        """Merge tickers and sectors from all cluster members into *best*."""
        merged_tickers: set[str] = set(best.tickers)
        merged_sectors: set[str] = set(best.sectors)

        for article in cluster:
            if article is best:
                continue
            merged_tickers.update(article.tickers)
            merged_sectors.update(article.sectors)
            # Promote to deal-related if any duplicate was flagged
            if article.is_deal_related:
                best.is_deal_related = True

        best.tickers = sorted(merged_tickers)
        best.sectors = sorted(merged_sectors)
