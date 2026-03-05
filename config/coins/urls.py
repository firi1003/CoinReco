from rest_framework import routers
from django.urls import include, path

from .views import (
    CoinDetailPage,
    CoinListPage,
    CoinViewSet,
    CommentViewSet,
    HomePageView,
    ProfilePage,
    ProfileView,
    RecommendationPage,
    RecommendationView,
    SectorDetailPage,
    SectorViewSet,
    RegisterView,
    UserLoginView,
    UserLogoutView,
    ProfileSetupView,
    ProfileAIAnalysisView,
    SectorAIAnalysisView,
)

router = routers.DefaultRouter()
router.register(r"coins", CoinViewSet, basename="coin")
router.register(r"sectors", SectorViewSet, basename="sector")
router.register(r"comments", CommentViewSet, basename="comment")

urlpatterns = [
    # Frontend pages
    path("", HomePageView.as_view(), name="home"),
    path("coins/", CoinListPage.as_view(), name="coin-list-page"),
    path("coins/<int:pk>/", CoinDetailPage.as_view(), name="coin-detail-page"),
    path("sectors/<int:pk>/", SectorDetailPage.as_view(), name="sector-detail-page"),
    path("recommendations/", RecommendationPage.as_view(), name="recommendations-page"),
    path("profile/page/", ProfilePage.as_view(), name="profile-page"),
    path("register/", RegisterView.as_view(), name="register"),
    path("register/setup/", ProfileSetupView.as_view(), name="profile-setup"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    # API
    path("api/", include(router.urls)),
    path("api/profile/", ProfileView.as_view(), name="profile"),
    path("api/profile/ai-analysis/", ProfileAIAnalysisView.as_view(), name="profile-ai-analysis"),
    path("api/recommendations/", RecommendationView.as_view(), name="recommendations-api"),
    path("api/sectors/<int:pk>/ai-analysis/", SectorAIAnalysisView.as_view(), name="sector-ai-analysis"),
]
