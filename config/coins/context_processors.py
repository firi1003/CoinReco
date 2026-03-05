from .models import Sector

def sector_data(request):
    """모든 페이지의 사이드바에서 사용할 섹터 데이터를 제공합니다."""
    if not request.user.is_authenticated:
        return {}
    
    # 실시간 데이터 계산 없이 오직 DB에서 섹터 목록만 가져옵니다.
    # 이것은 매우 빠른 쿼리이므로 로딩 지연을 일으키지 않습니다.
    return {
        'all_sectors': Sector.objects.all()
    }
