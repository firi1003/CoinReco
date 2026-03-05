from django.conf import settings
from django.db import models
from django.utils import timezone


class Sector(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class FeatureTag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class Coin(models.Model):
    LIQUIDITY_CHOICES = [
        ("high", "상"),
        ("mid", "중"),
        ("low", "하"),
    ]

    symbol = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    coingecko_id = models.CharField(max_length=100, blank=True)
    main_network = models.CharField(max_length=50, blank=True)
    launch_year = models.PositiveIntegerField(null=True, blank=True)
    liquidity_grade = models.CharField(
        max_length=10, choices=LIQUIDITY_CHOICES, default="mid"
    )
    market_cap = models.DecimalField(
        max_digits=30, decimal_places=2, null=True, blank=True
    )
    supply_total = models.DecimalField(
        max_digits=30, decimal_places=4, null=True, blank=True
    )
    supply_circulating = models.DecimalField(
        max_digits=30, decimal_places=4, null=True, blank=True
    )
    description = models.TextField(blank=True)
    website = models.URLField(max_length=500, blank=True)
    whitepaper = models.URLField(max_length=500, blank=True)
    image_url = models.URLField(max_length=500, blank=True)

    sectors = models.ManyToManyField(Sector, related_name="coins", blank=True)
    feature_tags = models.ManyToManyField(FeatureTag, related_name="coins", blank=True)

    def __str__(self) -> str:
        return f"{self.symbol} ({self.name})"


class Profile(models.Model):
    GENDER_CHOICES = [
        ("M", "남성"),
        ("F", "여성"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    birthdate = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    
    # 투자 성향 수치화 (1~10)
    risk_score = models.IntegerField(default=5)  # 위험도 정도
    trend_score = models.IntegerField(default=5) # 유행 민감도
    
    preferred_sectors = models.ManyToManyField(Sector, related_name="preferred_by", blank=True)
    avoided_sectors = models.ManyToManyField(Sector, related_name="avoided_by", blank=True)
    avatar = models.URLField(blank=True)

    def __str__(self) -> str:
        return f"Profile({self.user.username})"


class Comment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments"
    )
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name="comments")
    # 대댓글 기능을 위한 자기 참조 필드
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    like_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="like_comments", blank=True
    )
    dislike_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="dislike_comments", blank=True
    )

    class Meta:
        ordering = ["created_at"] # 오래된 댓글부터

    def __str__(self) -> str:
        return f"Comment({self.user} on {self.coin})"


class Recommendation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recs"
    )
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name="recs")
    total_score = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    
    # 상세 점수 (데이터 리포트용)
    sector_score = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    risk_score = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    trend_score = models.DecimalField(max_digits=6, decimal_places=3, default=0)

    is_avoided = models.BooleanField(default=False) # 비선호 섹터 포함 여부
    rank = models.IntegerField(default=0) # 추천 순위
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"{self.user} -> {self.coin} (Rank {self.rank})"


class CoinVote(models.Model):
    VOTE_CHOICES = [
        (True, "Buy"),
        (False, "Sell"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coin_votes"
    )
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name="votes")
    vote = models.BooleanField(choices=VOTE_CHOICES)  # True: Buy, False: Sell
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "coin")

    def __str__(self) -> str:
        v_str = "Buy" if self.vote else "Sell"
        return f"{self.user} voted {v_str} for {self.coin}"