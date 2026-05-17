"""사주팔자(四柱八字) 계산 핵심 로직.

- 천간(天干) 10개, 지지(地支) 12개를 기반으로 연·월·일·시주를 산출한다.
- 일간(日干)을 기준으로 오행(五行) 분포와 십성(十星)을 분석한다.
- 절기(節氣) 기준 월주 산정. 시주는 자시(子時)를 기준으로 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 기본 상수 정의
# ---------------------------------------------------------------------------

STEMS_HANJA = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
STEMS_HANGUL = ["갑", "을", "병", "정", "무", "기", "경", "신", "임", "계"]

BRANCHES_HANJA = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
BRANCHES_HANGUL = ["자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해"]
BRANCH_ANIMALS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]
BRANCH_ANIMAL_EMOJI = ["🐭", "🐮", "🐯", "🐰", "🐲", "🐍", "🐴", "🐑", "🐵", "🐔", "🐶", "🐷"]

# 천간 오행 (목·화·토·금·수)
STEM_ELEMENT = ["목", "목", "화", "화", "토", "토", "금", "금", "수", "수"]
# 천간 음양 (양·음)
STEM_YINYANG = ["양", "음", "양", "음", "양", "음", "양", "음", "양", "음"]

# 지지 오행
BRANCH_ELEMENT = ["수", "토", "목", "목", "토", "화", "화", "토", "금", "금", "토", "수"]
# 지지 음양 (자·인·진·오·신·술 = 양, 축·묘·사·미·유·해 = 음)
BRANCH_YINYANG = ["양", "음", "양", "음", "양", "음", "양", "음", "양", "음", "양", "음"]

# 지지 → 시간 범위 (시작시, 종료시) — 23시는 다음날 자시 시작
BRANCH_HOUR_RANGES = [
    (23, 1),   # 子 (자)
    (1, 3),    # 丑
    (3, 5),    # 寅
    (5, 7),    # 卯
    (7, 9),    # 辰
    (9, 11),   # 巳
    (11, 13),  # 午
    (13, 15),  # 未
    (15, 17),  # 申
    (17, 19),  # 酉
    (19, 21),  # 戌
    (21, 23),  # 亥
]

ELEMENT_COLOR = {
    "목": "#2E7D32",  # 짙은 초록
    "화": "#C62828",  # 적색
    "토": "#A1887F",  # 황토색
    "금": "#B0AAA2",  # 백금색
    "수": "#1565C0",  # 청색
}
ELEMENT_EMOJI = {"목": "🌳", "화": "🔥", "토": "⛰️", "금": "⚙️", "수": "💧"}

# 오행 상생/상극
SHENG = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}  # 생(生)
KE = {"목": "토", "토": "수", "수": "화", "화": "금", "금": "목"}  # 극(剋)

# 십성: 일간 기준 (같은 음양 / 다른 음양)
# 동일 오행: 비견 / 겁재
# 식상 (일간이 생함): 식신 / 상관
# 재성 (일간이 극함): 편재 / 정재
# 관성 (일간을 극함): 편관 / 정관
# 인성 (일간을 생함): 편인 / 정인

# 절기 진입 일자 (양력 기준, ±1일 오차 가능)
# 인월 시작 = 입춘 (~2/4), 묘월 = 경칩 (~3/6), 진월 = 청명 (~4/5),
# 사월 = 입하 (~5/6), 오월 = 망종 (~6/6), 미월 = 소서 (~7/7),
# 신월 = 입추 (~8/8), 유월 = 백로 (~9/8), 술월 = 한로 (~10/8),
# 해월 = 입동 (~11/7), 자월 = 대설 (~12/7), 축월 = 소한 (~1/6)
SOLAR_TERMS = [
    # (월, 일, 월주 지지 인덱스)
    (2, 4, 2),   # 입춘 → 寅(인) 시작
    (3, 6, 3),   # 경칩 → 卯
    (4, 5, 4),   # 청명 → 辰
    (5, 6, 5),   # 입하 → 巳
    (6, 6, 6),   # 망종 → 午
    (7, 7, 7),   # 소서 → 未
    (8, 8, 8),   # 입추 → 申
    (9, 8, 9),   # 백로 → 酉
    (10, 8, 10), # 한로 → 戌
    (11, 7, 11), # 입동 → 亥
    (12, 7, 0),  # 대설 → 子
    (1, 6, 1),   # 소한 → 丑
]


def _julian_day(y: int, m: int, d: int) -> int:
    """그레고리력 → Julian Day Number (정수, 정오 기준)."""
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524


def _month_branch_index(dt: date) -> int:
    """양력 일자에 해당하는 월지(月支) 인덱스. 절기 경계 적용."""
    y, m, d = dt.year, dt.month, dt.day
    # 1월은 소한 이후/이전으로 구분 (소한 이전은 전년의 자월=대설)
    if m == 1:
        if d >= 6:
            return 1  # 丑 (축, 소한~)
        else:
            return 0  # 子 (자, 대설~)
    # 같은 월 내에서 절기 진입 전이면 전월 지지 사용
    for (sm, sd, bi) in SOLAR_TERMS:
        if sm == m:
            if d >= sd:
                return bi
            else:
                # 절기 진입 전 → 전월 지지
                prev_idx = (bi - 1) % 12
                return prev_idx
    return 0  # 안전 fallback


def _year_pillar(dt: date, hour: Optional[int]) -> Tuple[int, int]:
    """연주(年柱)의 천간·지지 인덱스. 입춘 기준으로 해가 바뀜."""
    y = dt.year
    # 입춘(2/4) 이전이면 전년도
    if (dt.month, dt.day) < (2, 4):
        y -= 1
    stem_idx = (y - 4) % 10
    branch_idx = (y - 4) % 12
    return stem_idx, branch_idx


def _month_pillar(dt: date, year_stem_idx: int) -> Tuple[int, int]:
    """월주(月柱). 월간은 연간(年干)에 따라 결정 (오호둔법, 五虎遁法)."""
    month_branch_idx = _month_branch_index(dt)
    # 寅月(인월, idx=2)의 천간 시작: 갑·기년→丙寅, 을·경년→戊寅, 병·신년→庚寅,
    # 정·임년→壬寅, 무·계년→甲寅
    inwol_start = {0: 2, 1: 4, 2: 6, 3: 8, 4: 0,
                   5: 2, 6: 4, 7: 6, 8: 8, 9: 0}
    base = inwol_start[year_stem_idx]
    # 寅(2)부터 시작하므로 오프셋 계산
    offset = (month_branch_idx - 2) % 12
    month_stem_idx = (base + offset) % 10
    return month_stem_idx, month_branch_idx


def _day_pillar(dt: date) -> Tuple[int, int]:
    """일주(日柱). 율리우스일을 통해 60갑자 회전 산정.

    기준: 1900-01-01(양력) = 甲戌日 → JDN 2415021.
    """
    jdn = _julian_day(dt.year, dt.month, dt.day)
    diff = jdn - 2415021
    stem_idx = diff % 10
    branch_idx = (diff + 10) % 12  # 戌(10) 보정
    return stem_idx, branch_idx


def _hour_branch_index(hour: int) -> int:
    """시간(0-23) → 시지(時支) 인덱스. 23-1시는 자시."""
    if hour == 23 or hour == 0:
        return 0  # 子
    return ((hour + 1) // 2) % 12


def _hour_pillar(day_stem_idx: int, hour: Optional[int]) -> Optional[Tuple[int, int]]:
    """시주(時柱). 일간에 따라 자시 천간이 결정 (오자둔법, 五子遁法)."""
    if hour is None:
        return None
    branch_idx = _hour_branch_index(hour)
    # 자시 천간 시작: 갑·기일→甲子, 을·경일→丙子, 병·신일→戊子, 정·임일→庚子, 무·계일→壬子
    jasi_start = {0: 0, 1: 2, 2: 4, 3: 6, 4: 8,
                  5: 0, 6: 2, 7: 4, 8: 6, 9: 8}
    base = jasi_start[day_stem_idx]
    stem_idx = (base + branch_idx) % 10
    return stem_idx, branch_idx


# ---------------------------------------------------------------------------
# 십성 계산
# ---------------------------------------------------------------------------

def _ten_god(day_stem_idx: int, target_stem_idx: int) -> str:
    """일간 대비 천간의 십성 (육신, 六神) 명칭."""
    day_elem = STEM_ELEMENT[day_stem_idx]
    target_elem = STEM_ELEMENT[target_stem_idx]
    day_yy = STEM_YINYANG[day_stem_idx]
    target_yy = STEM_YINYANG[target_stem_idx]
    same_yy = (day_yy == target_yy)

    if day_elem == target_elem:
        return "비견" if same_yy else "겁재"
    if SHENG[day_elem] == target_elem:  # 일간이 생함
        return "식신" if same_yy else "상관"
    if KE[day_elem] == target_elem:  # 일간이 극함
        return "편재" if same_yy else "정재"
    if KE[target_elem] == day_elem:  # 일간을 극함
        return "편관(칠살)" if same_yy else "정관"
    if SHENG[target_elem] == day_elem:  # 일간을 생함
        return "편인" if same_yy else "정인"
    return "-"


def _branch_ten_god(day_stem_idx: int, branch_idx: int) -> str:
    """일간 대비 지지의 십성 (지지의 본기 오행 기준)."""
    day_elem = STEM_ELEMENT[day_stem_idx]
    target_elem = BRANCH_ELEMENT[branch_idx]
    day_yy = STEM_YINYANG[day_stem_idx]
    target_yy = BRANCH_YINYANG[branch_idx]
    same_yy = (day_yy == target_yy)

    if day_elem == target_elem:
        return "비견" if same_yy else "겁재"
    if SHENG[day_elem] == target_elem:
        return "식신" if same_yy else "상관"
    if KE[day_elem] == target_elem:
        return "편재" if same_yy else "정재"
    if KE[target_elem] == day_elem:
        return "편관" if same_yy else "정관"
    if SHENG[target_elem] == day_elem:
        return "편인" if same_yy else "정인"
    return "-"


# ---------------------------------------------------------------------------
# Saju 결과 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class Pillar:
    stem_idx: int
    branch_idx: int

    @property
    def hanja(self) -> str:
        return STEMS_HANJA[self.stem_idx] + BRANCHES_HANJA[self.branch_idx]

    @property
    def hangul(self) -> str:
        return STEMS_HANGUL[self.stem_idx] + BRANCHES_HANGUL[self.branch_idx]

    @property
    def stem_element(self) -> str:
        return STEM_ELEMENT[self.stem_idx]

    @property
    def branch_element(self) -> str:
        return BRANCH_ELEMENT[self.branch_idx]


@dataclass
class SajuResult:
    name: str
    hanja_name: str
    gender: str
    birth: datetime
    hour_known: bool

    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    hour_pillar: Optional[Pillar]

    element_counts: Dict[str, int]
    ten_gods: List[str]  # 천간 4개에 대한 십성 (연·월·일·시)
    branch_ten_gods: List[str]

    @property
    def day_master(self) -> str:
        return STEMS_HANGUL[self.day_pillar.stem_idx] + "(" + STEMS_HANJA[self.day_pillar.stem_idx] + ")"

    @property
    def day_master_element(self) -> str:
        return STEM_ELEMENT[self.day_pillar.stem_idx]

    @property
    def day_master_yinyang(self) -> str:
        return STEM_YINYANG[self.day_pillar.stem_idx]

    @property
    def zodiac(self) -> str:
        return BRANCH_ANIMALS[self.year_pillar.branch_idx]

    @property
    def zodiac_emoji(self) -> str:
        return BRANCH_ANIMAL_EMOJI[self.year_pillar.branch_idx]


def compute_saju(
    name: str,
    hanja_name: str,
    gender: str,
    birth: datetime,
    hour_known: bool,
) -> SajuResult:
    """사주팔자를 계산하고 결과 객체를 반환."""
    dt = birth.date()
    hour: Optional[int] = birth.hour if hour_known else None

    y_stem, y_branch = _year_pillar(dt, hour)
    m_stem, m_branch = _month_pillar(dt, y_stem)
    d_stem, d_branch = _day_pillar(dt)
    hp = _hour_pillar(d_stem, hour)

    yp = Pillar(y_stem, y_branch)
    mp = Pillar(m_stem, m_branch)
    dp = Pillar(d_stem, d_branch)
    hpillar = Pillar(*hp) if hp else None

    # 오행 분포 카운트
    counts = {"목": 0, "화": 0, "토": 0, "금": 0, "수": 0}
    for p in [yp, mp, dp, hpillar]:
        if p is None:
            continue
        counts[STEM_ELEMENT[p.stem_idx]] += 1
        counts[BRANCH_ELEMENT[p.branch_idx]] += 1

    # 십성 (천간 기준: 연·월·일·시간)
    ten_gods = []
    for p in [yp, mp, dp, hpillar]:
        if p is None:
            ten_gods.append("-")
            continue
        if p is dp:
            ten_gods.append("일간")
        else:
            ten_gods.append(_ten_god(d_stem, p.stem_idx))

    branch_ten_gods = []
    for p in [yp, mp, dp, hpillar]:
        if p is None:
            branch_ten_gods.append("-")
            continue
        branch_ten_gods.append(_branch_ten_god(d_stem, p.branch_idx))

    return SajuResult(
        name=name,
        hanja_name=hanja_name,
        gender=gender,
        birth=birth,
        hour_known=hour_known,
        year_pillar=yp,
        month_pillar=mp,
        day_pillar=dp,
        hour_pillar=hpillar,
        element_counts=counts,
        ten_gods=ten_gods,
        branch_ten_gods=branch_ten_gods,
    )


# ---------------------------------------------------------------------------
# 궁합 계산
# ---------------------------------------------------------------------------

# 삼합 (三合)
SAMHAP = [
    {2, 6, 10},   # 寅午戌 → 火국
    {5, 9, 1},    # 巳酉丑 → 金국
    {8, 0, 4},    # 申子辰 → 水국
    {11, 3, 7},   # 亥卯未 → 木국
]
# 육합 (六合)
YUKHAP = [{0, 1}, {2, 11}, {3, 10}, {4, 9}, {5, 8}, {6, 7}]
# 충 (沖) — 정반대
CHUNG = [{0, 6}, {1, 7}, {2, 8}, {3, 9}, {4, 10}, {5, 11}]
# 형 (刑)
HYUNG_PAIRS = [{0, 3}, {2, 5}, {5, 8}, {2, 8}, {1, 10}, {4, 4}, {6, 6}, {7, 7}, {11, 11}]


@dataclass
class CompatibilityResult:
    person_a: SajuResult
    person_b: SajuResult
    zodiac_score: int       # 0-100
    zodiac_relation: str
    day_master_score: int   # 0-100
    day_master_relation: str
    element_score: int      # 0-100
    element_balance: Dict[str, int]
    total_score: int
    summary: str
    detail: List[str]


def _zodiac_relation(b_a: int, b_b: int) -> Tuple[int, str]:
    pair = {b_a, b_b}
    if b_a == b_b:
        return 75, "동일 띠 (자형/비화) — 닮은 점이 많아 친구처럼 편안하나 자존심 대립 주의."
    for s in SAMHAP:
        if pair.issubset(s):
            return 95, "삼합(三合) — 최고의 띠 궁합. 서로의 부족함을 채워주며 큰 시너지를 만듭니다."
    for s in YUKHAP:
        if pair == s:
            return 90, "육합(六合) — 매우 좋은 띠 궁합. 정서적 교감과 안정감이 뛰어납니다."
    for s in CHUNG:
        if pair == s:
            return 30, "충(沖) — 가치관 충돌이 잦은 띠. 다툼이 많을 수 있으나 강한 끌림도 공존."
    for s in HYUNG_PAIRS:
        if pair == s:
            return 45, "형(刑) — 관계가 까칠하고 시비가 발생하기 쉬운 띠 조합."
    return 65, "보통 — 평이한 띠 궁합. 노력으로 충분히 좋은 관계를 만들 수 있습니다."


def _day_master_relation(a: int, b: int) -> Tuple[int, str]:
    """일간(日干) 오행 관계 점수."""
    ea, eb = STEM_ELEMENT[a], STEM_ELEMENT[b]
    yya, yyb = STEM_YINYANG[a], STEM_YINYANG[b]
    if ea == eb:
        if yya != yyb:
            return 80, f"동기(同氣) 음양조화 — 같은 {ea} 오행이지만 음양이 달라 균형이 좋습니다."
        return 60, f"동기 비화 — 같은 {ea} 오행으로 친근하나 경쟁심이 생길 수 있습니다."
    if SHENG[ea] == eb:
        return 85, f"상생(相生) — {ea}→{eb}. 본인이 상대를 길러주는 헌신적 관계."
    if SHENG[eb] == ea:
        return 90, f"상생(相生) — {eb}→{ea}. 상대로부터 도움을 받는 복된 관계."
    if KE[ea] == eb:
        return 50, f"상극(相剋) — {ea}이 {eb}을 극함. 주도하려 하나 갈등 가능."
    if KE[eb] == ea:
        return 45, f"상극(相剋) — {eb}이 {ea}을 극함. 압박감을 느낄 수 있는 관계."
    return 65, "중립 — 무난한 관계로 조율 여지가 있습니다."


def _element_complement(a_counts: Dict[str, int], b_counts: Dict[str, int]) -> Tuple[int, Dict[str, int]]:
    """오행 보완도 — 부족한 오행을 상대가 채워주는지 평가."""
    combined = {k: a_counts[k] + b_counts[k] for k in a_counts}
    ideal = sum(combined.values()) / 5
    # 표준편차 작을수록 좋음
    variance = sum((v - ideal) ** 2 for v in combined.values()) / 5
    # 0~100 매핑
    score = max(0, int(100 - variance * 8))
    return score, combined


def compute_compatibility(a: SajuResult, b: SajuResult) -> CompatibilityResult:
    z_score, z_text = _zodiac_relation(a.year_pillar.branch_idx, b.year_pillar.branch_idx)
    d_score, d_text = _day_master_relation(a.day_pillar.stem_idx, b.day_pillar.stem_idx)
    e_score, combined = _element_complement(a.element_counts, b.element_counts)

    total = int(z_score * 0.35 + d_score * 0.40 + e_score * 0.25)

    if total >= 85:
        summary = "🌟 천생연분 — 매우 뛰어난 궁합입니다."
    elif total >= 70:
        summary = "💕 길연 — 노력 없이도 잘 통하는 좋은 인연."
    elif total >= 55:
        summary = "🌱 보통 — 서로 이해하고 배려한다면 좋은 관계로 발전 가능."
    elif total >= 40:
        summary = "⚖️ 도전 — 가치관 차이가 있으나 노력으로 극복 가능."
    else:
        summary = "🌧️ 충돌 — 서로의 차이를 인정하는 지혜가 필요합니다."

    detail = [
        f"띠 궁합: **{a.zodiac_emoji}{a.zodiac}** × **{b.zodiac_emoji}{b.zodiac}** — {z_text}",
        f"일간 궁합: **{a.day_master}** × **{b.day_master}** — {d_text}",
        f"오행 보완도: 두 사주를 합쳤을 때 오행 균형이 {e_score}점입니다.",
    ]

    return CompatibilityResult(
        person_a=a,
        person_b=b,
        zodiac_score=z_score,
        zodiac_relation=z_text,
        day_master_score=d_score,
        day_master_relation=d_text,
        element_score=e_score,
        element_balance=combined,
        total_score=total,
        summary=summary,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# 한자 획수 사전 (한국 인명용 한자 일부)
# ---------------------------------------------------------------------------

HANJA_STROKES: Dict[str, int] = {
    # 성씨
    "金": 8, "李": 7, "朴": 6, "崔": 11, "鄭": 19, "姜": 9, "趙": 14, "尹": 4,
    "張": 11, "林": 8, "韓": 17, "吳": 7, "申": 5, "徐": 10, "權": 22, "黃": 12,
    "安": 6, "宋": 7, "柳": 9, "洪": 10, "全": 6, "高": 10, "文": 4, "梁": 11,
    "孫": 10, "裵": 14, "白": 5, "曺": 11, "許": 11, "劉": 15, "南": 9, "沈": 8,
    "盧": 16, "丁": 2, "河": 9, "郭": 11, "成": 7, "車": 7, "具": 8, "兪": 9,
    # 인명용 한자 (자주 쓰이는 글자)
    "民": 5, "俊": 9, "賢": 15, "智": 12, "宇": 6, "鎭": 18, "燮": 17, "煥": 13,
    "勳": 16, "晋": 10, "鎬": 18, "錫": 16, "炫": 9, "鉉": 13, "圭": 6, "敏": 11,
    "成": 7, "宰": 10, "成": 7, "正": 5, "東": 8, "南": 9, "北": 5, "西": 6,
    "中": 4, "大": 3, "小": 3, "上": 3, "下": 3, "天": 4, "地": 6, "山": 3,
    "水": 4, "火": 4, "木": 4, "金": 8, "土": 3, "日": 4, "月": 4, "星": 9,
    "光": 6, "明": 8, "亮": 9, "白": 5, "靑": 8, "靑": 8, "紅": 9, "綠": 14,
    "美": 9, "麗": 19, "佳": 8, "嘉": 14, "善": 12, "良": 7, "仁": 4, "義": 13,
    "禮": 18, "智": 12, "信": 9, "孝": 7, "誠": 14, "勇": 9, "和": 8, "平": 5,
    "安": 6, "康": 11, "壽": 14, "福": 14, "祿": 13, "貴": 12, "富": 12, "貞": 9,
    "順": 12, "淑": 12, "貞": 9, "賢": 15, "靜": 16, "雅": 12, "蘭": 23, "花": 10,
    "玉": 5, "珠": 11, "瑛": 13, "瑞": 14, "瓊": 20, "璇": 16, "璟": 17, "璿": 19,
    "英": 11, "榮": 14, "華": 14, "燕": 16, "鶴": 21, "鳳": 14, "麟": 23, "龍": 16,
    "虎": 8, "熊": 14, "鯨": 19, "鷹": 24, "鵬": 19, "雀": 11, "燕": 16, "鶯": 21,
    "民": 5, "國": 11, "邦": 7, "京": 8, "都": 12, "村": 7, "里": 7, "鄕": 13,
    "海": 11, "江": 7, "河": 9, "湖": 13, "波": 9, "瀛": 21, "洋": 10, "瀚": 20,
    "石": 5, "巖": 23, "岡": 8, "岸": 8, "峰": 10, "嶺": 17, "丘": 5, "原": 10,
    "森": 12, "樹": 16, "松": 8, "竹": 6, "梅": 11, "蘭": 23, "菊": 12, "蓮": 17,
    "桂": 10, "桐": 10, "楓": 13, "槐": 14, "栢": 10, "梧": 11, "柳": 9, "桃": 10,
    "雨": 8, "雲": 12, "雪": 11, "霜": 17, "霖": 16, "霞": 17, "霧": 19, "霓": 16,
    "風": 9, "雷": 13, "電": 13, "晴": 12, "暎": 13, "曜": 18, "曦": 20, "暖": 13,
    "永": 5, "遠": 14, "長": 8, "久": 3, "恒": 9, "常": 11, "始": 8, "終": 11,
    "新": 13, "舊": 18, "古": 5, "今": 4, "昔": 8, "現": 11, "來": 8, "去": 5,
    "心": 4, "情": 11, "意": 13, "志": 7, "思": 9, "想": 13, "念": 8, "願": 19,
    "夢": 14, "想": 13, "希": 7, "望": 11, "幸": 8, "福": 14, "樂": 15, "喜": 12,
    "勝": 12, "達": 13, "成": 7, "功": 5, "業": 13, "事": 8, "務": 11, "工": 3,
    "學": 16, "問": 11, "知": 8, "識": 19, "敎": 11, "育": 10, "書": 10, "文": 4,
    "詩": 13, "賦": 15, "歌": 14, "樂": 15, "畵": 13, "畫": 12, "藝": 21, "術": 11,
    "道": 16, "德": 15, "義": 13, "理": 12, "法": 9, "律": 9, "制": 8, "規": 11,
    "兒": 8, "童": 12, "子": 3, "女": 3, "男": 7, "婦": 11, "夫": 4, "妻": 8,
    "父": 4, "母": 5, "兄": 5, "弟": 7, "姉": 8, "妹": 8, "祖": 10, "宗": 8,
    "聖": 13, "賢": 15, "君": 7, "臣": 6, "王": 5, "帝": 9, "公": 4, "卿": 12,
    "將": 11, "相": 9, "尉": 11, "司": 5, "丞": 6, "卒": 8, "兵": 7, "士": 3,
}


def get_strokes(hanja: str) -> Optional[int]:
    return HANJA_STROKES.get(hanja)
