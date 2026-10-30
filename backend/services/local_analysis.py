"""本地分析服务 — 词频统计、图表数据生成，不调用 AI"""
import re
from collections import Counter
from datetime import datetime, timedelta

import jieba
import jieba.analyse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Article, ArticleKeyword, Keyword

# 中文停用词
STOPWORDS = set("""
的 了 和 是 在 与 或 也 都 就 还 又 才 等 把 被 让 使 给 对 从 向 为 以 按照 根据 由于 因此 因为 所以
这 那 这个 那个 这些 那些 什么 怎么 为什么 哪里 谁 其 此 该 某 每 各 另 另外 此外 同时 但是 然而 不过 虽然 如果
就是 都是 也是 还是 不是 会有 可以 应该 需要 已经 正在 将会 进行 通过 关于 对于 根据 以及 或者 并且 而且
一个 一种 一项 一些 一定 一直 不断 不断 以下 以上 之内 之外 其中 另外 此外 同时 已经 正在 将要
不 没 没有 无 非未 别 莫 勿
我 你 他 她 它 我们 你们 他们 她们 它们 自己 本身
说 看 做 想 知道 觉得 认为 发现 以及 进行 可以 应该 需要 已经
中 国 省 市 区 县 镇 村
将 被 把 给 对 从 向 为 以 跟 同 连 凭 靠
年 月 日 时 分 秒
个 件 条 篇 种 类 项
之 乎 者 也 于 以 因 故 而 则
有 无 多 少 大 小 好 坏 高 低 长 短 新 旧
""".split())

# 政策/资讯领域常见有意义词汇，提升权重
DOMAIN_BOOST = {"政策", "规划", "发展", "改革", "创新", "产业", "技术", "数据", "智能", "制造", "一体化"}


def _is_valid_word(word: str) -> bool:
    """过滤无效词"""
    if len(word) < 2:
        return False
    if word in STOPWORDS:
        return False
    if re.match(r"^[\d\.\-/%年月日时分秒]+$", word):
        return False
    if re.match(r"^[a-zA-Z]{1,3}$", word):
        return False
    return True


async def generate_local_wordcloud(
    db: AsyncSession, user_id: int, article_ids: list[int], keyword_id: int | None
) -> dict:
    """本地词频统计生成词云数据 — 使用 jieba 分词，不调用 AI"""
    # 获取文章内容
    if article_ids:
        result = await db.execute(
            select(Article)
            .where(Article.user_id == user_id, Article.id.in_(article_ids))
            .order_by(Article.crawl_date.desc())
        )
    elif keyword_id:
        result = await db.execute(
            select(Article)
            .join(ArticleKeyword, ArticleKeyword.article_id == Article.id)
            .where(Article.user_id == user_id, ArticleKeyword.keyword_id == keyword_id)
            .order_by(Article.crawl_date.desc())
            .limit(50)
        )
    else:
        result = await db.execute(
            select(Article).where(Article.user_id == user_id).order_by(Article.crawl_date.desc()).limit(50)
        )

    articles = result.scalars().all()
    if not articles:
        return {"error": "未找到可分析的文章内容"}

    # 合并文本
    full_text = "\n".join(f"{a.title}\n{a.content}" for a in articles if a.content)

    # 使用 jieba 提取关键词（TF-IDF）
    tags = jieba.analyse.extract_tags(full_text, topK=60, withWeight=True, allowPOS=("n", "vn", "v", "nz", "ns", "nt", "nr"))

    words = []
    for word, weight in tags:
        if not _is_valid_word(word):
            continue
        # 转换权重到 1-100 范围
        value = int(max(1, min(100, weight * 20)))
        if word in DOMAIN_BOOST:
            value = min(100, value + 15)
        words.append({"name": word, "value": value})

    # 如果 TF-IDF 结果太少，用词频补充
    if len(words) < 20:
        word_counts = Counter()
        for word in jieba.cut(full_text):
            if _is_valid_word(word):
                word_counts[word] += 1
        for word, count in word_counts.most_common(50):
            if not any(w["name"] == word for w in words):
                words.append({"name": word, "value": min(100, count * 5)})

    return {"words": words[:60], "total_articles": len(articles)}


async def generate_local_chart_data(
    db: AsyncSession, user_id: int, article_ids: list[int], keyword_id: int | None
) -> dict:
    """本地统计生成图表数据 — 不调用 AI"""
    # 获取文章
    if article_ids:
        result = await db.execute(
            select(Article)
            .where(Article.user_id == user_id, Article.id.in_(article_ids))
            .order_by(Article.crawl_date.desc())
        )
    elif keyword_id:
        result = await db.execute(
            select(Article)
            .join(ArticleKeyword, ArticleKeyword.article_id == Article.id)
            .where(Article.user_id == user_id, ArticleKeyword.keyword_id == keyword_id)
            .order_by(Article.crawl_date.desc())
            .limit(50)
        )
    else:
        result = await db.execute(
            select(Article).where(Article.user_id == user_id).order_by(Article.crawl_date.desc()).limit(50)
        )

    articles = result.scalars().all()
    if not articles:
        return {"error": "未找到可分析的文章内容"}

    # 1. 来源分布
    source_counter = Counter()
    for a in articles:
        name = a.source_name or "未知来源"
        # 简化域名
        if "." in name and len(name) > 20:
            parts = name.split(".")
            if len(parts) >= 2:
                name = parts[-2] + "." + parts[-1]
        source_counter[name] += 1
    source_distribution = [{"name": k, "value": v} for k, v in source_counter.most_common(10)]

    # 2. 类型分布
    type_counter = Counter(a.source_type for a in articles)
    type_labels = {"policy": "政策", "news": "资讯", "document": "文档", "pdf": "PDF"}
    topic_distribution = [{"name": type_labels.get(k, k), "value": v} for k, v in type_counter.most_common()]

    # 3. 关键词频次 — 用 jieba 分词
    full_text = "\n".join(f"{a.title}\n{a.content}" for a in articles if a.content)
    word_counts = Counter()
    for word in jieba.cut(full_text):
        if _is_valid_word(word):
            word_counts[word] += 1
    keyword_frequency = [{"name": k, "value": v} for k, v in word_counts.most_common(20)]

    # 4. 采集时间趋势（近30天）
    trend_counter = Counter()
    for a in articles:
        day = a.crawl_date.strftime("%Y-%m-%d") if a.crawl_date else None
        if day:
            trend_counter[day] += 1
    time_trend = [{"date": k, "count": v} for k, v in sorted(trend_counter.items())]

    # 5. 关联关键词分布
    kw_result = await db.execute(
        select(Keyword.keyword, func.count(Article.id))
        .join(ArticleKeyword, ArticleKeyword.keyword_id == Keyword.id)
        .join(Article, Article.id == ArticleKeyword.article_id)
        .where(Article.user_id == user_id)
        .group_by(Keyword.id, Keyword.keyword)
        .order_by(func.count(Article.id).desc())
        .limit(10)
    )
    keyword_distribution = [{"name": row[0], "value": row[1]} for row in kw_result.all()]

    return {
        "charts": {
            "source_distribution": source_distribution,
            "topic_distribution": topic_distribution,
            "keyword_frequency": keyword_frequency,
            "time_trend": time_trend,
            "keyword_distribution": keyword_distribution,
        },
        "total_articles": len(articles),
    }
