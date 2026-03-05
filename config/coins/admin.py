from django.contrib import admin
from .models import Coin, CoinVote, Comment, FeatureTag, Profile, Recommendation, Sector

@admin.register(CoinVote)
class CoinVoteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "coin", "vote", "created_at")
    list_filter = ("vote", "created_at")
    search_fields = ("user__username", "coin__symbol")

@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(FeatureTag)
class FeatureTagAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Coin)
class CoinAdmin(admin.ModelAdmin):
    list_display = ("id", "symbol", "name", "launch_year", "liquidity_grade", "market_cap")
    list_filter = ("liquidity_grade", "sectors")
    search_fields = ("symbol", "name")
    filter_horizontal = ("sectors", "feature_tags")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "full_name", "risk_score", "trend_score")
    search_fields = ("user__username", "full_name")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "coin", "parent", "created_at")
    list_filter = ("coin", "created_at")
    search_fields = ("content", "user__username")


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "coin", "total_score", "rank", "calculated_at")
    list_filter = ("calculated_at",)
    search_fields = ("user__username", "coin__symbol")
