from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Profile, Sector

User = get_user_model()

class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    full_name = forms.CharField(max_length=50, required=True, label="이름")
    phone = forms.CharField(max_length=20, required=True, label="전화번호")
    birthdate = forms.DateField(required=True, label="생년월일", widget=forms.DateInput(attrs={'type': 'date'}))
    gender = forms.ChoiceField(choices=Profile.GENDER_CHOICES, required=True, label="성별")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ("email",)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # 성향 정보 없이 프로필만 우선 생성
            Profile.objects.create(
                user=user,
                full_name=self.cleaned_data['full_name'],
                phone=self.cleaned_data['phone'],
                birthdate=self.cleaned_data['birthdate'],
                gender=self.cleaned_data['gender']
            )
        return user

class ProfileSetupForm(forms.ModelForm):
    """가입 후 투자 성향을 입력받는 전용 폼"""
    risk_score = forms.IntegerField(min_value=1, max_value=10, initial=5, label="위험 선호도 (1:보수 ~ 10:공격)")
    trend_score = forms.IntegerField(min_value=1, max_value=10, initial=5, label="유행 민감도 (1:둔감 ~ 10:민감)")
    
    preferred_sectors = forms.ModelMultipleChoiceField(
        queryset=Sector.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="선호 섹터"
    )
    avoided_sectors = forms.ModelMultipleChoiceField(
        queryset=Sector.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="비선호 섹터"
    )

    class Meta:
        model = Profile
        fields = ['risk_score', 'trend_score', 'preferred_sectors', 'avoided_sectors']
