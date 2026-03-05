from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    Coin,
    Comment,
    FeatureTag,
    Profile,
    Recommendation,
    Sector,
)


class SectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = ["id", "name", "description"]


class FeatureTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureTag
        fields = ["id", "name", "description"]


class CoinSerializer(serializers.ModelSerializer):
    sectors = SectorSerializer(many=True, read_only=True)
    feature_tags = FeatureTagSerializer(many=True, read_only=True)

    class Meta:
        model = Coin
        fields = [
            "id",
            "symbol",
            "name",
            "coingecko_id",
            "main_network",
            "launch_year",
            "liquidity_grade",
            "market_cap",
            "supply_total",
            "supply_circulating",
            "description",
            "website",
            "whitepaper",
            "sectors",
            "feature_tags",
        ]


class ProfileSerializer(serializers.ModelSerializer):
    preferred_sectors = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Sector.objects.all(), required=False
    )
    avoided_sectors = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Sector.objects.all(), required=False
    )

    class Meta:
        model = Profile
        fields = [
            "id",
            "full_name",
            "phone",
            "birthdate",
            "gender",
            "risk_score",
            "trend_score",
            "preferred_sectors",
            "avoided_sectors",
            "avatar",
        ]


class RecommendationSerializer(serializers.ModelSerializer):
    coin = CoinSerializer()

    class Meta:
        model = Recommendation
        fields = [
            "id",
            "coin",
            "total_score",
            "sector_score",
            "risk_score",
            "trend_score",
            "is_avoided",
            "rank",
            "calculated_at",
        ]


class CommentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "user", "coin", "parent", "content", "created_at", "replies"]
        read_only_fields = ["user", "created_at"]

    def get_replies(self, obj):
        if obj.replies.exists():
            return CommentSerializer(obj.replies.all(), many=True).data
        return []


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "username", "email"]
