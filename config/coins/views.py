from django.http import JsonResponse
from datetime import datetime

from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, DetailView, ListView, CreateView, UpdateView
from rest_framework import generics, mixins, permissions, status, viewsets
from .forms import RegistrationForm, ProfileSetupForm
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Coin, CoinVote, Comment, Profile, Recommendation, Sector
from .utils import get_coin_market_chart, get_coin_ohlc, get_ai_response, get_coins_markets_data
from .serializers import (
    CoinSerializer,
    CommentSerializer,
    ProfileSerializer,
    RecommendationSerializer,
    SectorSerializer,
)


class CoinViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Coin.objects.prefetch_related("sectors", "feature_tags").all()
    serializer_class = CoinSerializer

    @action(detail=True, methods=['get'])
    def ohlc(self, request, pk=None):
        coin = self.get_object()
        days = request.query_params.get('days', '1')
        chart_id = coin.coingecko_id or coin.symbol.lower()
        
        # 캔들차트에 필요한 OHLC 데이터만 가져오고, 사용하지 않는 market_chart 호출은 제거
        ohlc_data = get_coin_ohlc(chart_id, days=days)
        
        return Response({
            'ohlc': ohlc_data,
            'volumes': [] # 현재 프론트에서 사용하지 않으므로 빈 리스트 반환
        })

    @action(detail=True, methods=['get'])
    def ai_analysis(self, request, pk=None):
        coin = self.get_object()
        comments = coin.comments.filter(parent=None).select_related("user")[:3]
        
        sectors = ", ".join([s.name for s in coin.sectors.all()])
        recent_comments = "\n".join([f"- {c.content}" for c in comments])
        
        ai_prompt = f"""
        코인명: {coin.name} ({coin.symbol})
        섹터: {sectors}
        설명: {coin.description[:200]}...
        최근 커뮤니티 의견:
        {recent_comments if recent_comments else "의견 없음"}
        
        위 정보를 바탕으로 이 코인에 대한 '전문가 분석 리포트'를 3줄 내외로 작성해줘. 
        1.투자 주의사항, 2.향후 전망, 3.코인 섹션에 대한 설명을 해줘
        단락을 나눠서 답변해줘
        """
        analysis = get_ai_response(ai_prompt, "당신은 가상자산 투자 전문가입니다. 한국어로 전문적이고 신뢰감 있게 답변하세요.")
        return Response({'analysis': analysis})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def vote(self, request, pk=None):
        coin = self.get_object()
        vote_val = request.data.get('vote')  # Expected 'buy' or 'sell'
        
        if vote_val not in ['buy', 'sell']:
            return Response({'error': 'Invalid vote value'}, status=status.HTTP_400_BAD_REQUEST)
        
        is_buy = (vote_val == 'buy')
        
        # Update or create vote
        vote_obj, created = CoinVote.objects.update_or_create(
            user=request.user,
            coin=coin,
            defaults={'vote': is_buy}
        )
        
        # Recalculate percentages
        total_votes = coin.votes.count()
        buy_votes = coin.votes.filter(vote=True).count()
        buy_pct = (buy_votes / total_votes * 100) if total_votes > 0 else 0
        sell_pct = 100 - buy_pct if total_votes > 0 else 0
        
        return Response({
            'success': True,
            'buy_pct': round(buy_pct, 1),
            'sell_pct': round(sell_pct, 1),
            'total_votes': total_votes,
            'user_vote': 'buy' if is_buy else 'sell'
        })


class SectorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Sector.objects.all()
    serializer_class = SectorSerializer

    @action(detail=True, methods=['get'])
    def market_data(self, request, pk=None):
        sector = self.get_object()
        coins = Coin.objects.filter(sectors=sector).distinct()
        coin_ids = [c.coingecko_id for c in coins if c.coingecko_id]
        
        market_data = get_coins_markets_data(coin_ids)
        
        avg_change = 0
        if market_data:
            # 코인 이미지 URL 업데이트 (DB에 없을 경우)
            market_dict = {m['id']: m for m in market_data}
            for coin in coins:
                if coin.coingecko_id in market_dict:
                    m_data = market_dict[coin.coingecko_id]
                    if m_data.get('image') and not coin.image_url:
                        coin.image_url = m_data['image']
                        coin.save(update_fields=['image_url'])

            changes = [m.get('price_change_percentage_24h', 0) for m in market_data if m.get('price_change_percentage_24h') is not None]
            avg_change = sum(changes) / len(changes) if changes else 0
            
        return Response({
            'avg_change': round(avg_change, 2),
            'market_data': market_data[:10]
        })


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile


class ProfileAIAnalysisView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        pref = ", ".join([s.name for s in profile.preferred_sectors.all()])
        avoid = ", ".join([s.name for s in profile.avoided_sectors.all()])
        
        persona_prompt = f"""
        투자 성향 점수 (1-10): {profile.risk_score} (높을수록 공격적)
        유행 민감도 점수 (1-10): {profile.trend_score} (높을수록 최신 유행 선호)
        선호 섹터: {pref if pref else "없음"}
        기피 섹터: {avoid if avoid else "없음"}
        
        위 데이터를 분석해서 이 사용자의 '투자 페르소나'를 정의해줘. 
        별명(예: 신중한 거북이, 굶주린 사자 등)을 하나 지어주고, 
        이 성향에 맞는 투자 조언을 2문장으로 요약해줘.
        """
        ai_persona = get_ai_response(persona_prompt, "당신은 투자 심리 분석가입니다. 한국어로 친절하고 통찰력 있게 답변하세요.")
        return Response({'persona': ai_persona})


class RecommendationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        profile = request.user.profile
        pref_sectors = set(profile.preferred_sectors.values_list("id", flat=True))
        avoid_sectors = set(profile.avoided_sectors.values_list("id", flat=True))
        
        coins = Coin.objects.prefetch_related("sectors").all()
        scored_coins = []

        for coin in coins:
            score = 0.0
            s_score = 0.0
            r_score = 0.0
            t_score = 0.0
            is_avoided = False
            
            # 1. 섹터 점수 (가중치 높음)
            coin_sectors = set(coin.sectors.values_list("id", flat=True))
            if coin_sectors & pref_sectors:
                s_score += 5.0
            
            if coin_sectors & avoid_sectors:
                is_avoided = True
            
            # 2. 위험도 점수 (시가총액 기반)
            mcap = float(coin.market_cap) if coin.market_cap else 0
            if profile.risk_score <= 3: # 보수적
                if mcap > 10_000_000_000:
                    r_score += 3.0
                if coin.liquidity_grade == "high":
                    r_score += 2.0
            elif profile.risk_score >= 8: # 공격적
                if 0 < mcap < 1_000_000_000:
                    r_score += 3.0
                if coin.liquidity_grade == "low":
                    r_score += 2.0
            else: # 중립
                if 1_000_000_000 <= mcap <= 10_000_000_000:
                    r_score += 3.0
                if coin.liquidity_grade == "mid":
                    r_score += 2.0

            # 3. 유행 민감도 (발행연도 기반)
            year = coin.launch_year or 2020
            if profile.trend_score >= 8: # 유행 민감
                if year >= 2023:
                    t_score += 3.0
                if coin.liquidity_grade == "high":
                    t_score += 2.0
            elif profile.trend_score <= 3: # 근본 중시
                if year <= 2017:
                    t_score += 3.0
            else: # 중립
                if 2018 <= year <= 2022:
                    t_score += 3.0

            score = s_score + r_score + t_score
            scored_coins.append({
                "coin": coin,
                "total_score": score,
                "s_score": s_score,
                "r_score": r_score,
                "t_score": t_score,
                "is_avoided": is_avoided
            })

        # 점수 순으로 정렬 후 상위 10개 추출
        scored_coins.sort(key=lambda x: x["total_score"], reverse=True)
        top_10 = scored_coins[:10]

        # 기존 추천 기록 삭제 후 새로 저장
        Recommendation.objects.filter(user=request.user).delete()
        
        recs = []
        for i, item in enumerate(top_10):
            rec = Recommendation.objects.create(
                user=request.user,
                coin=item["coin"],
                total_score=item["total_score"],
                sector_score=item["s_score"],
                risk_score=item["r_score"],
                trend_score=item["t_score"],
                is_avoided=item["is_avoided"],
                rank=i + 1
            )
            recs.append(rec)

        serializer = RecommendationSerializer(recs, many=True)
        return Response(serializer.data)


# --- Authentication Views ---
class RegisterView(CreateView):
    template_name = "registration/register.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("profile-setup")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'redirect_url': str(self.success_url)})
        return redirect(self.success_url)

    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        return super().form_invalid(form)


class ProfileSetupView(UpdateView):
    template_name = "registration/profile_setup.html"
    form_class = ProfileSetupForm
    success_url = reverse_lazy("home")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['no_sidebar'] = True
        return context

    def get_object(self):
        return self.request.user.profile

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'redirect_url': str(self.success_url)})
        return redirect(self.success_url)

    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        return super().form_invalid(form)


class UserLoginView(LoginView):
    template_name = "registration/login.html"

    def form_valid(self, form):
        login(self.request, form.get_user())
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'redirect_url': str(self.get_success_url())})
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False, 
                'errors': {'username': ['아이디 또는 비밀번호가 올바르지 않습니다.']}
            }, status=400)
        return super().form_invalid(form)


class UserLogoutView(LogoutView):
    next_page = "home"


class IsOwnerOrReadOnly(permissions.BasePermission):
    """작성자만 수정/삭제가 가능하도록 하는 커스텀 권한입니다."""
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def get_queryset(self):
        coin_id = self.request.query_params.get("coin")
        # 최상위 댓글만 반환 (대댓글은 Serializer에서 처리)
        qs = Comment.objects.filter(parent=None).select_related("user", "coin").all()
        if coin_id:
            qs = qs.filter(coin_id=coin_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# --- Frontend pages (templates) ---
class HomePageView(TemplateView):
    def get_template_names(self):
        if self.request.user.is_authenticated:
            return ["home.html"]
        return ["landing.html"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            ctx["top_coins"] = Coin.objects.all()[:12]
            ctx["sectors"] = Sector.objects.all()
        else:
            # 랜딩 페이지용 코인 목록
            ctx["display_coins"] = Coin.objects.all().order_by('?')[:100]
        return ctx


class CoinDetailPage(DetailView):
    model = Coin
    template_name = "coin_detail.html"
    context_object_name = "coin"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["comments"] = self.object.comments.filter(parent=None).select_related("user")
        
        # 투표 통계 계산
        total_votes = self.object.votes.count()
        buy_votes = self.object.votes.filter(vote=True).count()
        buy_pct = (buy_votes / total_votes * 100) if total_votes > 0 else 50 # 기본값 50
        sell_pct = 100 - buy_pct if total_votes > 0 else 50
        
        ctx["voting_stats"] = {
            "total_votes": total_votes,
            "buy_pct": round(buy_pct, 1),
            "sell_pct": round(sell_pct, 1),
        }
        
        # 현재 사용자의 투표 여부
        if self.request.user.is_authenticated:
            user_vote = self.object.votes.filter(user=self.request.user).first()
            ctx["user_vote"] = "buy" if user_vote and user_vote.vote else ("sell" if user_vote else None)

        # Real-time chart and AI analysis
        # coingecko_id가 없으면 소문자 심볼을 사용하도록 보완
        # 서버 사이드에서의 get_coin_market_chart 중복 호출 제거 (프론트엔드에서 AJAX로 처리함)
        
        # 이미지 URL이 없을 경우에만 마켓 데이터를 통해 가져오기
        if not self.object.image_url:
            target_id = self.object.coingecko_id or self.object.symbol.lower()
            m_data_list = get_coins_markets_data([target_id])
            if m_data_list:
                self.object.image_url = m_data_list[0].get('image', '')
                self.object.save(update_fields=['image_url'])

        # 한화 시가총액 계산 (환율 1,400원 가정)
        if self.object.market_cap:
            ctx["market_cap_krw"] = float(self.object.market_cap) * 1400
            
        return ctx


class CoinListPage(ListView):
    model = Coin
    template_name = "coin_list.html"
    context_object_name = "coins"
    paginate_by = 20  # 한 페이지에 20개씩 표시

    def get_queryset(self):
        return Coin.objects.all().order_by("symbol")


class RecommendationPage(ListView):
    model = Recommendation
    template_name = "recommendations.html"
    context_object_name = "recs"

    def get_queryset(self):
        user = self.request.user if self.request.user.is_authenticated else None
        qs = Recommendation.objects.select_related("coin").prefetch_related("coin__sectors")
        if user:
            qs = qs.filter(user=user).select_related("user__profile").prefetch_related("user__profile__preferred_sectors")
        return qs[:50]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_profile"] = (
            self.request.user.is_authenticated
            and Profile.objects.filter(user=self.request.user).exists()
        )
        return ctx


class ProfilePage(TemplateView):
    template_name = "profile.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        profile = None
        if self.request.user.is_authenticated:
            profile, _ = Profile.objects.get_or_create(user=self.request.user)
        ctx["profile"] = profile
        ctx["sectors"] = Sector.objects.all()

        return ctx

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': '로그인이 필요합니다.'}, status=403)
        
        profile = request.user.profile
        risk_score = request.POST.get('risk_score')
        trend_score = request.POST.get('trend_score')
        pref_sectors = request.POST.getlist('preferred_sectors')
        avoid_sectors = request.POST.getlist('avoided_sectors')

        try:
            profile.risk_score = int(risk_score)
            profile.trend_score = int(trend_score)
            profile.save()

            profile.preferred_sectors.set(pref_sectors)
            profile.avoided_sectors.set(avoid_sectors)

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


class SectorDetailPage(DetailView):
    model = Sector
    template_name = "sector_detail.html"
    context_object_name = "sector"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # 섹터별 고정 설명 정의 (로딩 지연 없음, 일관성 유지)
        SECTOR_DESCRIPTIONS = {
            "레이어1": (
                "레이어1은 블록체인의 기본 프로토콜과 구조를 의미합니다.\n"
                "비트코인, 이더리움 같은 블록체인 네트워크가 대표적입니다.\n"
                "트랜잭션 처리, 블록 생성, 보안 등 모든 주요 기능이 레이어1에서 처리됩니다.\n"
                "이 네트워크는 탈중앙화와 보안성을 중시하며, 모든 거래 내역을 분산된 방식으로 저장하고 검증합니다.\n"
                "하지만, 트랜잭션 속도나 수수료에서 한계가 있어 확장성 문제를 겪고 있습니다.\n"
                "레이어2 솔루션을 통해 이 문제를 해결하려는 시도가 이어지고 있습니다.\n"
                "그럼에도 불구하고 레이어1은 블록체인의 기반을 이루는 핵심적인 기술입니다.\n"
                "블록체인의 주요 역할을 수행하는 중요한 계층입니다."
            ),
            "레이어2": (
                "레이어2는 레이어1 블록체인의 성능 문제를 해결하기 위한 기술입니다.\n"
                "트랜잭션 속도를 높이고, 수수료를 줄이며, 더 많은 거래를 처리할 수 있도록 돕습니다.\n"
                "대표적인 레이어2 기술로는 상태 채널과 롤업이 있습니다.\n"
                "상태 채널은 트랜잭션을 오프체인에서 처리하고, 결과만 레이어1에 기록하는 방식입니다.\n"
                "롤업은 여러 트랜잭션을 묶어 처리하고, 그 결과를 블록체인에 기록하는 방식으로 성능을 개선합니다.\n"
                "레이어2는 확장성을 높이는 데 중요한 역할을 하며, 이더리움과 같은 플랫폼에서 활발히 사용되고 있습니다.\n"
                "이 기술을 통해 빠르고 저렴한 거래가 가능해지며, 블록체인의 효율성을 크게 향상시킬 수 있습니다.\n"
                "레이어2는 블록체인의 성능 향상에 중요한 기여를 하고 있습니다."
            ),
            "롤업": (
                "롤업은 레이어2 기술 중 하나로, 여러 트랜잭션을 오프체인에서 처리하고, 그 결과만 레이어1에 기록하는 방식입니다.\n"
                "대표적으로 옵티미스틱 롤업과 zk롤업이 있습니다.\n"
                "옵티미스틱 롤업은 트랜잭션이 유효하다고 가정하고, 이후 문제가 발생하면 이를 해결하는 방식입니다.\n"
                "반면 zk롤업은 영지식 증명을 통해 트랜잭션의 유효성을 검증하고 결과를 블록체인에 기록합니다.\n"
                "롤업은 확장성을 극대화하고, 거래 비용을 대폭 절감하는 데 기여합니다.\n"
                "이 기술은 이더리움의 성능을 크게 향상시킬 수 있는 잠재력을 가지고 있습니다.\n"
                "롤업은 블록체인의 효율성을 높이고, 거래 처리 속도를 획기적으로 개선합니다.\n"
                "이더리움과 같은 플랫폼에서 성능을 강화하는 중요한 역할을 합니다."
            ),
            "디파이": (
                "디파이(탈중앙화 금융)는 중앙화된 금융기관 없이 블록체인 상에서 금융 서비스를 제공하는 시스템입니다.\n"
                "사용자들은 스마트 계약을 통해 대출, 예금, 거래 등 다양한 금융 서비스를 이용할 수 있습니다.\n"
                "디파이는 탈중앙화된 금융 생태계를 구축하며, 은행이나 중개자 없이 거래가 이루어집니다.\n"
                "대표적인 디파이 플랫폼으로는 Uniswap, MakerDAO, Compound 등이 있으며, 이들은 블록체인의 스마트 계약을 통해 자동화된 금융 거래를 지원합니다.\n"
                "디파이는 투명성과 접근성을 제공하며, 누구나 금융 서비스에 참여할 수 있는 기회를 제공합니다.\n"
                "이더리움 기반에서 활발히 운영되며, 기존 금융 시스템을 탈중앙화하려는 중요한 시도로 자리잡고 있습니다.\n"
                "디파이는 블록체인의 실용화를 이끌어가는 중요한 분야입니다.\n"
                "블록체인의 금융 분야에서 디파이의 역할은 더욱 중요해질 것입니다."
            ),
            "스테이블코인": (
                "스테이블코인은 가치 변동성이 적은 암호화폐로, 법정 화폐나 자산에 연동되어 안정적인 가치를 유지합니다.\n"
                "대표적으로 테더(USDT), 다이(DAI), USD Coin(USDC) 등이 있습니다.\n"
                "스테이블코인은 암호화폐의 변동성 문제를 해결하며, 결제 수단이나 디파이 플랫폼에서 중요한 역할을 합니다.\n"
                "예를 들어, 1 USDT는 항상 1 USD와 같은 가치를 유지하려고 합니다.\n"
                "이를 통해 거래자는 변동성이 큰 암호화폐 대신 안정적인 디지털 자산을 사용할 수 있습니다.\n"
                "스테이블코인은 법정 화폐와 연동되어 있어, 암호화폐 시장의 변동성을 줄이고 더 안전한 환경을 제공합니다.\n"
                "스테이블코인은 블록체인 기반에서 안정적이고 유용한 자산으로 자리잡고 있습니다.\n"
                "이는 디지털 경제에서 중요한 역할을 하게 됩니다."
            ),
            "NFT": (
                "NFT는 대체 불가능한 디지털 자산을 나타내는 토큰입니다.\n"
                "예술 작품, 음악, 영상 등 다양한 형태의 창작물에 대한 소유권을 증명하는 데 사용됩니다.\n"
                "NFT는 블록체인에서 발행되며, 각 토큰은 고유하고 다시 대체할 수 없는 특성을 지닙니다.\n"
                "이로 인해 예술가와 창작자는 자신의 작품에 대한 디지털 소유권을 명확히 할 수 있습니다.\n"
                "NFT는 주로 이더리움 네트워크에서 발행되며, 디지털 예술 및 게임 아이템 등에서 활발히 사용됩니다.\n"
                "이 기술은 디지털 자산의 거래를 가능하게 하고, 새로운 경제 모델을 제공합니다.\n"
                "NFT는 가치 증명과 소유권 거래를 통해 문화 산업 및 창작 경제에 큰 영향을 미칩니다.\n"
                "이는 블록체인의 새로운 가능성을 열어가는 중요한 기술입니다."
            ),
            "게임": (
                "블록체인 게임은 디지털 자산을 게임 내에서 사용하고 거래할 수 있는 시스템입니다.\n"
                "게임 내 아이템은 NFT로 발행되어 소유권을 증명하며, 사용자는 이를 외부에서 거래하거나 이용할 수 있습니다.\n"
                "게임은 주로 Play-to-Earn(P2E) 모델을 통해, 사용자가 게임을 플레이하면서 실제 가치를 얻을 수 있는 기회를 제공합니다.\n"
                "예를 들어, Axie Infinity는 플레이어들이 게임 내 아이템을 거래하고, 암호화폐를 획득하는 방식으로 운영됩니다.\n"
                "블록체인 게임은 탈중앙화된 경제 시스템을 기반으로 하며, 사용자들에게 더 큰 자유도와 보상을 제공합니다.\n"
                "이 모델은 게임 경제와 디지털 자산을 결합하여 새로운 형태의 게임 경험을 제공합니다.\n"
                "게임 산업은 블록체인과 결합하여 혁신적인 변화를 일으키고 있습니다.\n"
                "블록체인 기술을 통해 게임 내 자산의 소유권을 증명하고, 거래할 수 있게 되었습니다."
            ),
            "인프라": (
                "블록체인 인프라는 블록체인 네트워크의 기반을 구성하는 다양한 요소를 포함합니다.\n"
                "노드, API, 지갑 서비스 등 블록체인 시스템의 필수적인 구성 요소들이 여기에 포함됩니다.\n"
                "인프라는 블록체인 보안성을 강화하고, 확장성을 향상시키며, 다양한 블록체인 서비스가 원활하게 운영될 수 있도록 지원합니다.\n"
                "예를 들어, 이더리움과 같은 플랫폼은 스마트 계약을 처리할 수 있는 강력한 인프라를 제공합니다.\n"
                "블록체인의 분산화를 유지하면서도 효율적인 거래 처리와 빠른 트랜잭션을 가능하게 하는 기술들이 발전하고 있습니다.\n"
                "블록체인 인프라는 블록체인 생태계의 핵심을 이루며, 서비스와 플랫폼의 기반을 다집니다.\n"
                "블록체인의 발전과 함께 인프라는 점점 더 중요해지고 있습니다.\n"
                "블록체인의 성장을 지원하는 중요한 기술적 기반입니다."
            ),
            "오라클": (
                "오라클은 블록체인 외부의 데이터를 블록체인으로 전달하는 서비스입니다.\n"
                "스마트 계약은 블록체인 내부에서만 실행되므로, 외부 데이터를 처리하려면 오라클을 통해 데이터를 가져와야 합니다.\n"
                "예를 들어, 실시간 금융 데이터나 날씨 정보 등을 블록체인 스마트 계약에서 사용할 수 있게 해줍니다.\n"
                "오라클은 블록체인과 현실 세계를 연결하는 중요한 역할을 하며, 분산형 데이터 제공 방식으로 신뢰성을 보장합니다.\n"
                "Chainlink와 같은 오라클 서비스는 블록체인에 안전하고 정확한 외부 정보를 제공합니다.\n"
                "오라클을 통해 스마트 계약은 실시간 데이터를 활용하여 더 복잡한 논리를 처리할 수 있습니다.\n"
                "블록체인 생태계에서 오라클은 외부 세계와의 연결을 가능하게 하여, 블록체인의 활용 범위를 확장하는 데 중요한 기술입니다.\n"
                "오라클은 블록체인 기술의 응용 가능성을 넓히는 필수적인 요소입니다."
            ),
            "인덱싱": (
                "인덱싱은 블록체인 데이터를 효율적으로 검색하고 분석할 수 있도록 만드는 기술입니다.\n"
                "블록체인 네트워크에서 생성된 데이터를 구조화하여 빠르게 접근할 수 있게 도와줍니다.\n"
                "예를 들어, 블록체인에 기록된 거래 내역을 쉽게 조회하고 분석할 수 있도록 하는 역할을 합니다.\n"
                "인덱싱은 트랜잭션 기록, 스마트 계약 호출 등을 체계적으로 정리하여 빠른 검색과 처리를 가능하게 합니다.\n"
                "The Graph와 같은 인덱싱 프로토콜은 블록체인 데이터를 구조화된 형태로 제공하여 dApp 개발자들이 보다 쉽게 데이터를 활용할 수 있도록 합니다.\n"
                "블록체인의 검색성과 분석 가능성을 높여줌으로써, 블록체인 생태계에서 효율적인 데이터 활용이 가능합니다.\n"
                "이 기술은 블록체인에서 대규모 데이터를 다루는 애플리케이션에서 필수적인 역할을 합니다.\n"
                "인덱싱은 데이터 접근성과 효율성을 개선하는 데 중요한 기여를 합니다."
            ),
            "AI": (
                "AI는 인공지능 기술로, 머신러닝, 자연어 처리 등 다양한 알고리즘을 통해 데이터를 분석하고 의사 결정을 내립니다.\n"
                "블록체인과 결합되면, 스마트 계약의 자동화, 데이터 분석, 예측 모델 개발 등에 활용될 수 있습니다.\n"
                "AI는 블록체인 기술을 활용하여 데이터 보안과 프라이버시 보호를 강화하는 데 기여할 수 있습니다.\n"
                "블록체인의 불변성과 투명성을 AI가 활용하면, 더 정확한 분석과 예측이 가능합니다.\n"
                "예를 들어, AI는 거래 데이터를 분석하여 사기 거래를 예측하거나 시장 변동성을 예측할 수 있습니다.\n"
                "AI와 블록체인 기술의 결합은 스마트 계약의 실행을 더욱 지능화하고, 자동화된 결정 시스템을 구현하는 데 유용합니다.\n"
                "또한 AI는 블록체인 네트워크의 효율성과 확장성을 향상시킬 수 있는 중요한 기술로 자리잡고 있습니다.\n"
                "AI는 블록체인 시스템의 지능화와 자동화를 가능하게 하여 더 스마트한 생태계를 구축하는 데 중요한 역할을 합니다."
            ),
            "데이터": (
                "데이터 블록체인은 분산형 데이터 저장소로, 데이터를 안전하고 투명하게 보관합니다.\n"
                "블록체인 기술을 활용하면, 데이터를 중앙화된 서버가 아닌 분산된 네트워크에서 보관할 수 있습니다.\n"
                "이로 인해 데이터의 검증 가능성과 보안성이 크게 향상됩니다.\n"
                "데이터 블록체인은 특히 의료 데이터, 금융 데이터, 개인 정보 등을 안전하게 처리하는 데 유용합니다.\n"
                "블록체인의 불변성을 통해, 데이터의 위변조나 삭제를 방지할 수 있습니다.\n"
                "분산형 데이터 저장소는 개인 데이터 보호와 프라이버시 측면에서 중요한 역할을 합니다.\n"
                "이 기술은 다양한 산업에서 신뢰성 있는 데이터 관리 솔루션으로 활용되고 있습니다.\n"
                "데이터 블록체인은 투명한 데이터 관리와 효율적인 데이터 접근을 가능하게 하여 블록체인 생태계의 핵심 요소로 자리잡고 있습니다."
            ),
            "RWA": (
                "RWA는 현실 세계의 자산을 디지털 자산으로 변환하여 블록체인에서 거래하는 방식입니다.\n"
                "예를 들어, 부동산이나 금 같은 실제 자산을 블록체인에 토큰화하여 디지털 자산으로 거래할 수 있게 됩니다.\n"
                "RWA는 전통적인 자산의 유동성을 높이고, 더 많은 사람들이 자산에 투자할 수 있도록 돕습니다.\n"
                "블록체인을 사용하면 자산의 소유권과 거래 내역을 투명하게 기록할 수 있어, 신뢰성을 강화할 수 있습니다.\n"
                "RWA의 도입은 자산의 글로벌화와 분산 투자를 가능하게 합니다.\n"
                "이러한 방식은 특히 부동산 시장에서 중요한 변화를 일으킬 수 있으며, 시장 접근성을 향상시킵니다.\n"
                "RWA는 블록체인 기술을 통해 전통적인 자산을 디지털화하고, 투자 기회를 확대하는 중요한 기술입니다.\n"
                "이는 자산 관리 및 투자 방식에 혁신적인 변화를 가져올 수 있습니다."
            ),
            "토큰화": (
                "토큰화는 자산을 디지털 토큰으로 변환하는 과정입니다.\n"
                "이는 부동산, 주식, 예술 작품 등 다양한 자산을 디지털화하여 거래할 수 있게 합니다.\n"
                "토큰화된 자산은 소액 투자가 가능하며, 이를 통해 더 많은 사람들이 다양한 자산에 접근할 수 있습니다.\n"
                "블록체인 기술은 토큰화된 자산에 대해 소유권을 명확하게 기록하고, 안전하게 거래할 수 있게 해줍니다.\n"
                "또한, 자산의 유동성을 높이고, 투자자들에게 더 많은 선택의 폭을 제공합니다.\n"
                "토큰화는 자산 거래의 효율성과 투명성을 높이는 중요한 기술로 자리잡고 있습니다.\n"
                "블록체인의 불변성을 활용하여 토큰화된 자산은 위변조를 방지하고, 보다 안전한 거래 환경을 제공합니다.\n"
                "토큰화는 기존 자산 시장의 혁신적인 변화를 이끌 중요한 기술입니다."
            ),
            "프라이버시": (
                "프라이버시 기술은 블록체인에서 개인 정보를 보호하는 방법을 제공합니다.\n"
                "블록체인 거래는 본래 투명성을 목표로 하지만, 일부 경우에는 개인정보 보호가 필요할 수 있습니다.\n"
                "zk-SNARKs와 같은 기술을 사용하여 거래 내역을 익명화하거나 숨길 수 있습니다.\n"
                "이를 통해 개인 정보 보호와 거래의 프라이버시를 유지하면서도, 블록체인의 투명성을 보장할 수 있습니다.\n"
                "프라이버시 기술은 금융 거래, 의료 데이터, 개인 식별 정보 등을 보호하는 데 필수적입니다.\n"
                "Monero와 같은 암호화폐는 프라이버시를 최우선으로 고려한 블록체인으로, 거래의 비공개성을 강조합니다.\n"
                "프라이버시 기술은 블록체인 사용자가 자신의 정보를 통제할 수 있게 하여 보안성을 높입니다.\n"
                "프라이버시는 블록체인의 보안성과 기밀성을 중요한 요소로 만들어, 많은 산업에 채택되고 있습니다."
            ),
            "소셜": (
                "블록체인 기반의 소셜 네트워크는 중앙화된 플랫폼과 달리 사용자 데이터를 자기 소유할 수 있게 해줍니다.\n"
                "사용자는 자신이 생성한 콘텐츠와 정보를 자유롭게 관리하고, 이를 거래할 수 있는 권리를 가집니다.\n"
                "이러한 시스템은 개인정보 보호와 탈중앙화된 데이터 관리를 가능하게 합니다.\n"
                "Steemit과 같은 블록체인 기반 소셜 미디어는 사용자들이 콘텐츠를 생산하고, 보상을 받을 수 있는 구조를 제공합니다.\n"
                "소셜 미디어의 통제권을 사용자에게 돌려주며, 광고와 중앙화된 통제에서 벗어난 자율적인 플랫폼을 제공합니다.\n"
                "블록체인의 투명성을 통해, 소셜 미디어 상의 정보 조작을 방지할 수 있습니다.\n"
                "소셜 네트워크의 탈중앙화는 사용자 권한을 강화하고, 새로운 방식의 콘텐츠 유통을 가능하게 합니다.\n"
                "소셜 블록체인은 프라이버시와 자유를 지키면서 사용자들에게 새로운 디지털 환경을 제공합니다."
            ),
            "밈": (
                "밈 코인은 주로 유머와 사회적 트렌드를 반영하는 암호화폐입니다.\n"
                "대표적인 예로 도지코인이 있으며, 커뮤니티 기반으로 인기를 끌고 있습니다.\n"
                "밈 코인은 가치 변동성이 크지만, 소셜 미디어에서 큰 영향을 미치고 있습니다.\n"
                "이들은 주로 재미와 문화적 트렌드를 기반으로 하여, 빠르게 확산되고 인기를 끌기도 합니다.\n"
                "밈 코인은 그 자체로 투자 대상이 아니라, 커뮤니티와의 소통과 문화적 상징으로서 가치가 높습니다.\n"
                "사회적 이슈나 유명인사의 발언에 따라 가격이 급등하거나 급락하기도 하며, 그만큼 위험성이 큰 자산입니다.\n"
                "밈 코인의 인기는 디지털 문화와 소셜 미디어의 영향을 받으며, 암호화폐 시장에서 중요한 문화적 현상을 만들어가고 있습니다.\n"
                "그럼에도 불구하고 밈 코인은 투자로서의 가치보다 커뮤니티와의 연결이 더 중요한 특징을 지닙니다."
            ),
            "기타": (
                "기타 항목은 블록체인 기술과 관련된 다양한 새로운 또는 실험적인 프로젝트들을 포함합니다.\n"
                "특정 분야에 국한되지 않고, 기술적 혁신을 통해 블록체인 가능성을 탐구하는 다양한 아이디어들이 여기에 속할 수 있습니다.\n"
                "이는 새로운 경제 모델이나 산업 혁신을 위한 기술들로, 블록체인 기술이 적용될 수 있는 다양한 가능성을 시험하는 분야입니다.\n"
                "이 범주에는 게임, 예술, 의료, 공공 서비스 등 블록체인의 응용 가능성에 대한 새로운 접근이 포함됩니다.\n"
                "블록체인 기술은 기존 산업에 혁신을 일으키는 다양한 실험을 가능하게 하며, 새로운 시장을 창출할 수 있습니다.\n"
                "이러한 기타 기술들은 블록체인의 무한한 가능성을 확장하고, 혁신적인 시스템을 실현하는 데 기여합니다.\n"
                "이 분야는 기술의 실험적 발전을 포함하며, 블록체인 생태계의 미래를 이끌 수 있는 중요한 역할을 합니다.\n"
                "기타는 블록체인 생태계에서 새로운 트렌드와 창의적인 해결책을 제시하는 중요한 분야입니다."
            ),
        }

        # DB에 설명이 없으면 매핑된 고정 설명 사용
        if not self.object.description:
            ctx["sector_description"] = SECTOR_DESCRIPTIONS.get(
                self.object.name, 
                "이 섹션의 주요 자산들을 분석하고 시장 흐름을 추적하여 최적의 통찰력을 제공합니다."
            )
        else:
            ctx["sector_description"] = self.object.description

        coins = Coin.objects.filter(sectors=self.object).distinct()
        ctx["display_coins"] = coins
        
        # 실시간 데이터는 프론트엔드에서 비동기(AJAX)로 가져오도록 변경하여 페이지 전환 속도 최적화
        ctx["avg_change"] = None
        ctx["market_data"] = None
            
        return ctx


class SectorAIAnalysisView(APIView):
    """섹터별 AI 브리핑 및 가상 뉴스를 비동기로 생성합니다."""
    def get(self, request, pk):
        sector = get_object_or_404(Sector, pk=pk)
        coins = Coin.objects.filter(sectors=sector).distinct()
        
        coin_names = ", ".join([c.name for c in coins[:5]])
        prompt = f"가상자산 시장에서 '{sector.name}' 섹터({coin_names} 등 포함)의 현재 트렌드와 관련하여 가상의 2가지 뉴스 헤드라인과 가상의 url을 작성해줘. 그리고 현재 섹터의 트렌드를 요약해줘."
        
        ai_brief = get_ai_response(prompt)
        return Response({'ai_brief': ai_brief})
