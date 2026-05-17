"""명리원(命理院) — 사주팔자·궁합·성명학 종합 분석 웹앱.

전통 명리학과 성명학 이론에 기반해 사주팔자(四柱八字), 궁합, 성명 81수리를 분석합니다.
"""

from __future__ import annotations

from datetime import datetime, date, time

import pandas as pd
import streamlit as st

from saju_core import (
    BRANCHES_HANGUL,
    BRANCHES_HANJA,
    BRANCH_HOUR_RANGES,
    ELEMENT_COLOR,
    ELEMENT_EMOJI,
    HANJA_STROKES,
    STEMS_HANGUL,
    STEMS_HANJA,
    SajuResult,
    compute_compatibility,
    compute_saju,
    get_strokes,
)
from interpretations import (
    DAY_MASTER_TRAITS,
    TEN_GOD_MEANING,
    element_advice,
    element_analysis,
    num81_fortune,
)

# ---------------------------------------------------------------------------
# 페이지 설정 & 글로벌 CSS
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="명리원 · 사주팔자 · 궁합 · 작명",
    page_icon="☯️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;800&family=Nanum+Myeongjo:wght@400;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Serif KR', 'Nanum Myeongjo', serif;
}

.stApp {
    background:
      radial-gradient(circle at 20% 10%, rgba(212, 175, 55, 0.08), transparent 40%),
      radial-gradient(circle at 80% 90%, rgba(178, 34, 52, 0.07), transparent 50%),
      linear-gradient(180deg, #1a0e0a 0%, #221511 50%, #1a0e0a 100%);
    color: #f4ecd8;
}

/* 상단 헤더 */
.hero {
    text-align: center;
    padding: 30px 10px 10px;
    border-bottom: 1px solid rgba(212, 175, 55, 0.25);
    margin-bottom: 30px;
}
.hero h1 {
    font-family: 'Nanum Myeongjo', serif;
    font-size: 3.2rem;
    font-weight: 800;
    color: #d4af37;
    letter-spacing: 0.4rem;
    margin: 0;
    text-shadow: 0 2px 10px rgba(0,0,0,0.5);
}
.hero h1 .ko { color: #f4ecd8; font-size: 1.5rem; letter-spacing: 0.2rem; }
.hero p {
    color: #c9b890;
    margin-top: 8px;
    font-size: 1rem;
    letter-spacing: 0.15em;
}

/* 카드 */
.card {
    background: linear-gradient(145deg, rgba(40, 26, 20, 0.85), rgba(28, 18, 14, 0.92));
    border: 1px solid rgba(212, 175, 55, 0.25);
    border-radius: 16px;
    padding: 26px 30px;
    margin: 14px 0;
    box-shadow: 0 8px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(212,175,55,0.1);
}
.card h3 {
    color: #d4af37;
    margin-top: 0;
    font-family: 'Nanum Myeongjo', serif;
    border-bottom: 1px solid rgba(212, 175, 55, 0.2);
    padding-bottom: 10px;
}

/* 사주 8글자 표시 */
.pillar-table {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin: 20px 0;
}
.pillar-cell {
    text-align: center;
    padding: 18px 8px;
    border-radius: 12px;
    background: linear-gradient(160deg, rgba(40,30,22,0.9), rgba(22,16,12,0.95));
    border: 1px solid rgba(212, 175, 55, 0.2);
    position: relative;
}
.pillar-cell .label {
    font-size: 0.85rem;
    color: #c9b890;
    margin-bottom: 8px;
    letter-spacing: 0.2em;
}
.pillar-cell .hanja {
    font-family: 'Nanum Myeongjo', serif;
    font-size: 3rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 6px 0;
}
.pillar-cell .hanja .stem { display:block; }
.pillar-cell .hanja .branch { display:block; }
.pillar-cell .hangul {
    font-size: 0.9rem;
    color: #c9b890;
    margin-top: 4px;
}
.pillar-cell .ten-god {
    font-size: 0.75rem;
    color: #d4af37;
    margin-top: 6px;
    opacity: 0.85;
}

/* 오행 색상 박스 */
.elem-mok { color: #6abf69 !important; }
.elem-hwa { color: #ff6e6e !important; }
.elem-to  { color: #d2a679 !important; }
.elem-geum{ color: #e0e0e0 !important; }
.elem-su  { color: #6aa9ff !important; }

/* 점수 바 */
.score-bar {
    background: rgba(255,255,255,0.08);
    height: 14px;
    border-radius: 8px;
    overflow: hidden;
    margin: 6px 0;
}
.score-fill {
    height: 100%;
    background: linear-gradient(90deg, #d4af37, #f1d97a);
    border-radius: 8px;
}

/* 탭 스타일 */
.stTabs [data-baseweb="tab-list"] {
    gap: 10px;
    justify-content: center;
}
.stTabs [data-baseweb="tab"] {
    background: rgba(40,30,22,0.6);
    border: 1px solid rgba(212,175,55,0.2);
    border-radius: 10px;
    color: #c9b890;
    padding: 10px 22px;
    font-weight: 600;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #4a2d1a, #6b3e22) !important;
    color: #d4af37 !important;
    border: 1px solid #d4af37 !important;
}

/* 입력 위젯 */
.stTextInput input, .stDateInput input, .stSelectbox div[data-baseweb="select"] > div {
    background: rgba(20,12,8,0.7) !important;
    color: #f4ecd8 !important;
    border-color: rgba(212,175,55,0.25) !important;
}
label, .stMarkdown p { color: #f4ecd8; }
.stButton button {
    background: linear-gradient(135deg, #8b1a1a, #5a0e0e);
    color: #f1d97a;
    border: 1px solid #d4af37;
    border-radius: 10px;
    padding: 10px 28px;
    font-weight: 700;
    letter-spacing: 0.1em;
    font-family: 'Noto Serif KR', serif;
}
.stButton button:hover {
    background: linear-gradient(135deg, #a52828, #6e1414);
    color: #fff;
}

/* 큰 숫자 점수 */
.big-score {
    font-size: 5rem;
    font-weight: 800;
    color: #d4af37;
    text-align: center;
    font-family: 'Nanum Myeongjo', serif;
    line-height: 1;
}
.big-score-label { text-align: center; color: #c9b890; letter-spacing: 0.3em; }

/* 푸터 */
.footer {
    text-align: center;
    color: #8a7855;
    font-size: 0.85rem;
    margin-top: 50px;
    padding: 20px;
    border-top: 1px solid rgba(212,175,55,0.15);
}

/* 데이터프레임 다크 */
.stDataFrame { background: rgba(20,12,8,0.5); }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="hero">
        <h1>命理院<br><span class="ko">명 리 원</span></h1>
        <p>사주팔자 · 궁 합 · 작 명 ☯ 전통 명리학 종합 분석</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 유틸 — UI 렌더링
# ---------------------------------------------------------------------------


def _elem_class(elem: str) -> str:
    return {"목": "elem-mok", "화": "elem-hwa", "토": "elem-to",
            "금": "elem-geum", "수": "elem-su"}.get(elem, "")


def render_pillars(saju: SajuResult) -> None:
    labels = ["時 (시주)", "日 (일주)", "月 (월주)", "年 (연주)"]
    pillars = [saju.hour_pillar, saju.day_pillar, saju.month_pillar, saju.year_pillar]
    # 십성: [year, month, day, hour] 순으로 들어 있음 → 역순 매칭
    ten_gods_order = list(reversed(saju.ten_gods))  # [hour, day, month, year]
    branch_tg_order = list(reversed(saju.branch_ten_gods))

    cells = []
    for i, (label, p) in enumerate(zip(labels, pillars)):
        if p is None:
            cells.append(f"""
                <div class="pillar-cell">
                    <div class="label">{label}</div>
                    <div class="hanja" style="color:#5a4a35;">
                        <span class="stem">?</span>
                        <span class="branch">?</span>
                    </div>
                    <div class="hangul">시간 미상</div>
                </div>
            """)
            continue
        stem_cls = _elem_class(p.stem_element)
        branch_cls = _elem_class(p.branch_element)
        cells.append(f"""
            <div class="pillar-cell">
                <div class="label">{label}</div>
                <div class="ten-god">{ten_gods_order[i]}</div>
                <div class="hanja">
                    <span class="stem {stem_cls}">{STEMS_HANJA[p.stem_idx]}</span>
                    <span class="branch {branch_cls}">{BRANCHES_HANJA[p.branch_idx]}</span>
                </div>
                <div class="hangul">
                    {STEMS_HANGUL[p.stem_idx]}({p.stem_element}) · {BRANCHES_HANGUL[p.branch_idx]}({p.branch_element})
                </div>
                <div class="ten-god">{branch_tg_order[i]}</div>
            </div>
        """)
    st.markdown(f"<div class='pillar-table'>{''.join(cells)}</div>", unsafe_allow_html=True)


def render_elements(saju: SajuResult) -> None:
    counts = saju.element_counts
    total = sum(counts.values()) or 1
    cols = st.columns(5)
    for i, elem in enumerate(["목", "화", "토", "금", "수"]):
        with cols[i]:
            cnt = counts[elem]
            pct = int(cnt / total * 100)
            color = ELEMENT_COLOR[elem]
            emoji = ELEMENT_EMOJI[elem]
            st.markdown(
                f"""
                <div class="card" style="text-align:center; padding:18px;">
                    <div style="font-size:2rem">{emoji}</div>
                    <div style="font-size:1.4rem; font-weight:800; color:{color};">{elem}</div>
                    <div style="font-size:2rem; font-weight:800; color:#d4af37;">{cnt}</div>
                    <div style="color:#c9b890; font-size:0.85rem;">{pct}%</div>
                    <div class="score-bar" style="margin-top:8px;">
                        <div class="score-fill" style="width:{pct}%; background:{color};"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_score(label: str, score: int) -> None:
    st.markdown(
        f"""
        <div style="margin: 10px 0;">
            <div style="display:flex; justify-content:space-between; color:#c9b890;">
                <span>{label}</span><span style="color:#d4af37; font-weight:800;">{score}점</span>
            </div>
            <div class="score-bar"><div class="score-fill" style="width:{score}%;"></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 입력 폼
# ---------------------------------------------------------------------------

def saju_input_form(prefix: str, default_name: str = "") -> dict:
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("이름 (한글)", value=default_name, key=f"{prefix}_name")
        gender = st.selectbox("성별", ["남자", "여자"], key=f"{prefix}_gender")
    with c2:
        hanja_name = st.text_input("한자 이름 (선택)", value="", key=f"{prefix}_hanja",
                                    placeholder="예) 金正民")
        birth_date = st.date_input(
            "생년월일 (양력)",
            value=date(1990, 1, 1),
            min_value=date(1900, 1, 1),
            max_value=date(2100, 12, 31),
            key=f"{prefix}_date",
        )

    c3, c4 = st.columns([1, 2])
    with c3:
        hour_known = st.checkbox("태어난 시 알고 있음", value=True, key=f"{prefix}_hk")
    with c4:
        if hour_known:
            hour_options = []
            for i, (start, end) in enumerate(BRANCH_HOUR_RANGES):
                hangul = BRANCHES_HANGUL[i]
                hanja = BRANCHES_HANJA[i]
                if start > end:
                    rng = f"{start:02d}:00 ~ 익일 {end:02d}:00"
                else:
                    rng = f"{start:02d}:00 ~ {end:02d}:00"
                hour_options.append(f"{hangul}시 ({hanja}時) — {rng}")
            sel = st.selectbox("태어난 시간 (한국시 기준)", hour_options, key=f"{prefix}_hour")
            hour_idx = hour_options.index(sel)
            # 시간 인덱스 → 시작시간으로 변환 (자시=23시, 축시=1시 등)
            start_h = BRANCH_HOUR_RANGES[hour_idx][0]
            hour_val = start_h if start_h != 23 else 23
        else:
            hour_val = 12  # placeholder, 사용 안됨

    birth_dt = datetime.combine(birth_date, time(hour_val % 24, 30))
    return {
        "name": name or "익명",
        "hanja_name": hanja_name,
        "gender": gender,
        "birth": birth_dt,
        "hour_known": hour_known,
    }


# ---------------------------------------------------------------------------
# 결과 렌더링 — 사주풀이
# ---------------------------------------------------------------------------

def render_saju_full(saju: SajuResult) -> None:
    dm_hangul = STEMS_HANGUL[saju.day_pillar.stem_idx]
    dm_traits = DAY_MASTER_TRAITS[dm_hangul]

    # 인적사항 / 일주
    st.markdown(
        f"""
        <div class="card">
            <h3>📜 사주 명식 — {saju.name}{' (' + saju.hanja_name + ')' if saju.hanja_name else ''}</h3>
            <p style="color:#c9b890;">
                생년월일: {saju.birth.strftime('%Y년 %m월 %d일')} ({saju.gender}) ·
                {saju.zodiac_emoji} <b>{saju.zodiac}띠</b> ·
                일간(日干) <b style="color:#d4af37;">{saju.day_master}</b>
                ({saju.day_master_yinyang} · {saju.day_master_element})
                {' · 시 미상' if not saju.hour_known else ''}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 8글자 표시
    st.markdown("<div class='card'><h3>🪧 사주팔자 (四柱八字)</h3>", unsafe_allow_html=True)
    render_pillars(saju)
    st.markdown(
        "<p style='color:#8a7855; font-size:0.8rem; text-align:center;'>"
        "※ 왼쪽부터 시주 · 일주 · 월주 · 연주 (전통 명리 표기법)</p></div>",
        unsafe_allow_html=True,
    )

    # 오행
    st.markdown("<div class='card'><h3>🌳🔥⛰️⚙️💧 오행(五行) 분포</h3>", unsafe_allow_html=True)
    render_elements(saju)
    st.markdown("</div>", unsafe_allow_html=True)

    # 오행 해설
    st.markdown(
        f"""
        <div class="card">
            <h3>⚖️ 오행 균형 분석</h3>
            <p>{element_analysis(saju.element_counts, saju.day_master_element)}</p>
            <p style="color:#c9b890;"><b>{saju.day_master_element} 일간을 위한 조언:</b><br>
            {element_advice(saju.day_master_element)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 일주 풀이
    st.markdown(
        f"""
        <div class="card">
            <h3>🎭 일간 {saju.day_master} 풀이</h3>
            <p><b>성격:</b> {dm_traits['성격']}</p>
            <p><b>장점:</b> {dm_traits['장점']}</p>
            <p><b>단점:</b> {dm_traits['단점']}</p>
            <p><b>적합한 직업:</b> {dm_traits['직업']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 십성표
    rows = []
    labels = ["연주(年柱)", "월주(月柱)", "일주(日柱)", "시주(時柱)"]
    pillars = [saju.year_pillar, saju.month_pillar, saju.day_pillar, saju.hour_pillar]
    for label, p, tg, btg in zip(labels, pillars, saju.ten_gods, saju.branch_ten_gods):
        if p is None:
            rows.append([label, "-", "-", "-", "-", "시 미상", "-"])
            continue
        rows.append([
            label,
            STEMS_HANJA[p.stem_idx] + " (" + STEMS_HANGUL[p.stem_idx] + ")",
            STEM_HUMAN(p.stem_idx),
            tg,
            BRANCHES_HANJA[p.branch_idx] + " (" + BRANCHES_HANGUL[p.branch_idx] + ")",
            BRANCH_HUMAN(p.branch_idx),
            btg,
        ])
    df = pd.DataFrame(rows, columns=["구분", "천간", "음양·오행", "천간 십성", "지지", "음양·오행", "지지 십성"])
    st.markdown("<div class='card'><h3>📊 천간 · 지지 · 십성(十星) 상세</h3>", unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("💡 십성(十星)의 의미"):
        for tg in set(saju.ten_gods + saju.branch_ten_gods):
            if tg in ("-", "일간"):
                continue
            st.markdown(f"**{tg}** — {TEN_GOD_MEANING.get(tg, '')}")
    st.markdown("</div>", unsafe_allow_html=True)


# 헬퍼: 인덱스 → 음양·오행 텍스트
def STEM_HUMAN(idx: int) -> str:
    from saju_core import STEM_ELEMENT, STEM_YINYANG
    return f"{STEM_YINYANG[idx]}·{STEM_ELEMENT[idx]}"


def BRANCH_HUMAN(idx: int) -> str:
    from saju_core import BRANCH_ELEMENT, BRANCH_YINYANG
    return f"{BRANCH_YINYANG[idx]}·{BRANCH_ELEMENT[idx]}"


# ---------------------------------------------------------------------------
# 탭 구성
# ---------------------------------------------------------------------------

tab_saju, tab_match, tab_name, tab_about = st.tabs(
    ["🔮 사주팔자", "💞 궁합", "✍️ 작명·성명학", "ℹ️ 명리원 소개"]
)

# ============================== 1. 사주 ==============================
with tab_saju:
    st.markdown(
        "<div class='card'><h3>📥 사주 입력</h3>"
        "<p style='color:#c9b890;'>이름·생년월일·태어난 시각을 입력하시면 사주팔자(四柱八字), "
        "오행 분포, 십성(十星), 일간 풀이를 상세히 분석해 드립니다.</p>",
        unsafe_allow_html=True,
    )
    data = saju_input_form("single", default_name="")
    submitted = st.button("사주 풀이 보기", key="single_submit", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        saju = compute_saju(**data)
        render_saju_full(saju)

# ============================== 2. 궁합 ==============================
with tab_match:
    st.markdown(
        "<div class='card'><h3>💘 남녀 사주 입력</h3>"
        "<p style='color:#c9b890;'>두 사람의 정보를 입력하시면 띠 궁합 · 일간 궁합 · "
        "오행 보완도를 종합한 궁합 점수를 산정해 드립니다.</p></div>",
        unsafe_allow_html=True,
    )

    cA, cB = st.columns(2)
    with cA:
        st.markdown("<div class='card'><h3>🤵 남자</h3>", unsafe_allow_html=True)
        male = saju_input_form("male", default_name="")
        male["gender"] = "남자"
        st.markdown("</div>", unsafe_allow_html=True)
    with cB:
        st.markdown("<div class='card'><h3>👰 여자</h3>", unsafe_allow_html=True)
        female = saju_input_form("female", default_name="")
        female["gender"] = "여자"
        st.markdown("</div>", unsafe_allow_html=True)

    if st.button("궁합 보기", key="match_submit", use_container_width=True):
        a = compute_saju(**male)
        b = compute_saju(**female)
        comp = compute_compatibility(a, b)

        st.markdown(
            f"""
            <div class="card">
                <h3>🎯 종합 궁합 결과</h3>
                <div class="big-score">{comp.total_score}<span style="font-size:2rem; color:#c9b890;">/100</span></div>
                <div class="big-score-label">{comp.summary}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='card'><h3>📐 세부 점수</h3>", unsafe_allow_html=True)
        render_score("띠 궁합 (35%)", comp.zodiac_score)
        render_score("일간 궁합 (40%)", comp.day_master_score)
        render_score("오행 보완도 (25%)", comp.element_score)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='card'><h3>📜 상세 풀이</h3>", unsafe_allow_html=True)
        for d in comp.detail:
            st.markdown(f"- {d}")
        st.markdown("</div>", unsafe_allow_html=True)

        # 합산 오행 균형
        st.markdown("<div class='card'><h3>🌈 두 사주 오행 합산</h3>", unsafe_allow_html=True)
        cols = st.columns(5)
        total = sum(comp.element_balance.values()) or 1
        for i, elem in enumerate(["목", "화", "토", "금", "수"]):
            with cols[i]:
                cnt = comp.element_balance[elem]
                pct = int(cnt / total * 100)
                st.markdown(
                    f"""
                    <div style="text-align:center; padding:14px;">
                        <div style="font-size:1.8rem;">{ELEMENT_EMOJI[elem]}</div>
                        <div style="font-size:1.2rem; color:{ELEMENT_COLOR[elem]}; font-weight:700;">{elem}</div>
                        <div style="font-size:1.6rem; font-weight:800; color:#d4af37;">{cnt}</div>
                        <div class="score-bar"><div class="score-fill" style="width:{pct}%; background:{ELEMENT_COLOR[elem]};"></div></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)

        # 각자의 사주 명식 펼치기
        with st.expander(f"📜 {a.name}의 상세 사주"):
            render_saju_full(a)
        with st.expander(f"📜 {b.name}의 상세 사주"):
            render_saju_full(b)

# ============================== 3. 성명학 ==============================
with tab_name:
    st.markdown(
        "<div class='card'><h3>✒️ 한자 성명 입력</h3>"
        "<p style='color:#c9b890;'>한자 이름을 입력하시면 천격(天格)·인격(人格)·지격(地格)·"
        "외격(外格)·총격(總格)의 5격 81수리 길흉을 분석합니다.</p>",
        unsafe_allow_html=True,
    )

    hanja_input = st.text_input(
        "한자 이름 (성+이름)",
        value="金正民",
        help="예) 金正民, 李英姬. 사전에 없는 한자는 아래 표에서 수동 입력하세요.",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if hanja_input:
        chars = [c for c in hanja_input.strip() if c.strip()]
        if len(chars) < 2:
            st.warning("한자 이름은 2글자 이상 입력해 주세요.")
        else:
            st.markdown("<div class='card'><h3>📝 한자별 획수</h3>", unsafe_allow_html=True)
            strokes = []
            cols = st.columns(len(chars))
            for i, ch in enumerate(chars):
                with cols[i]:
                    default = get_strokes(ch) or 0
                    s = st.number_input(
                        f"{ch}",
                        min_value=1,
                        max_value=40,
                        value=default if default > 0 else 8,
                        key=f"stroke_{i}",
                        help="사전에 등록된 한자는 자동 입력됩니다.",
                    )
                    strokes.append(int(s))
            st.markdown("</div>", unsafe_allow_html=True)

            # 성명학 5격 계산 (한국식 작명)
            # - 성씨가 한 글자라고 가정
            # - 천격 = 성씨 획수 + 1 (또는 그대로) — 본 앱은 성씨 획수 자체를 사용
            # - 인격 = 성씨 + 이름 첫글자
            # - 지격 = 이름 전체 합
            # - 외격 = 총격 - 인격 + 1
            # - 총격 = 모든 획수의 합
            surname_strokes = strokes[0]
            given_strokes = strokes[1:]
            chun = surname_strokes  # 天格
            ein = surname_strokes + given_strokes[0]  # 人格
            ji = sum(given_strokes) if len(given_strokes) >= 2 else given_strokes[0] + 1  # 地格
            chong = sum(strokes)  # 總格
            oe = chong - ein + 1  # 外格

            data_grid = [
                ("天格 (천격)", chun, "조상·부모운 — 성씨에서 유래"),
                ("人格 (인격)", ein, "주운(主運) — 30대 이전의 핵심 운, 성격·재능"),
                ("地格 (지격)", ji, "초년운 — 청소년기 학업·가정"),
                ("外格 (외격)", oe, "사회운 — 대인관계·외부환경"),
                ("總格 (총격)", chong, "말년운·전체 인생의 큰 흐름"),
            ]

            st.markdown("<div class='card'><h3>🔯 5격(五格) 81수리 풀이</h3>", unsafe_allow_html=True)
            for label, n, desc in data_grid:
                fortune, expl = num81_fortune(n)
                color = {"대길": "#d4af37", "길": "#6abf69",
                         "보통": "#c9b890", "흉": "#ff6e6e"}.get(fortune, "#c9b890")
                st.markdown(
                    f"""
                    <div style="margin: 12px 0; padding: 14px;
                         border-left: 4px solid {color};
                         background: rgba(20,12,8,0.5); border-radius: 8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <b style="color:#d4af37; font-size:1.1rem;">{label}</b>
                            <span style="color:{color}; font-weight:800; font-size:1.2rem;">
                                {n}수 · {fortune}
                            </span>
                        </div>
                        <p style="color:#c9b890; margin:6px 0 0 0;">{desc}</p>
                        <p style="margin:6px 0 0 0;">{expl}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)

            # 한자 음양 분석
            yin_yang = []
            for s in strokes:
                yin_yang.append("양(陽)" if s % 2 == 1 else "음(陰)")
            st.markdown(
                f"""
                <div class="card">
                    <h3>☯️ 음양(陰陽) 배합</h3>
                    <p>{' · '.join([f'{c}({s}획·{yy})' for c, s, yy in zip(chars, strokes, yin_yang)])}</p>
                    <p style="color:#c9b890;">
                    이상적 배합: 음양이 모두 같으면 단조롭고, 적절히 섞이면 조화로운 작명입니다.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ============================== 4. 소개 ==============================
with tab_about:
    st.markdown(
        """
        <div class="card">
            <h3>ℹ️ 명리원(命理院)이란</h3>
            <p>명리원은 동양 명리학(命理學)의 사주팔자(四柱八字), 궁합론, 성명학(姓名學)을
            현대 웹 환경에서 누구나 손쉽게 이용할 수 있도록 만든 종합 분석 서비스입니다.</p>
            <ul>
                <li><b>사주팔자</b> — 생년월일시를 천간(天干)·지지(地支) 8글자로 환산, 일간 기준
                오행과 십성을 분석합니다. 절기(節氣)를 기준으로 월주를 산정해 전통 명리의
                정통성을 따릅니다.</li>
                <li><b>궁합</b> — 띠 궁합(삼합·육합·충), 일간 오행 상생상극, 오행 보완도를
                가중 평균해 점수화합니다.</li>
                <li><b>성명학</b> — 한자 획수를 기반으로 천격·인격·지격·외격·총격의
                5격을 산정하고 81수리 길흉을 매핑합니다.</li>
            </ul>
            <h3>📚 이론적 근거</h3>
            <p>본 서비스는 자평진전(子平眞詮), 명리정종(命理正宗), 적천수(滴天髓) 등
            동양 명리 고전의 원리와 현대 통계 자료를 종합해 설계되었습니다.</p>
            <h3>⚠️ 사용 시 유의사항</h3>
            <ul>
                <li>본 서비스는 <b>참고 목적</b>이며, 인생의 중대한 결정을 대신하지 않습니다.</li>
                <li>입력하신 정보는 서버에 저장되지 않습니다.</li>
                <li>절기 경계일(±1일) 및 일출 전 출생자의 경우 결과가 ±1일 차이날 수 있습니다.</li>
                <li>한국 표준시 기준이며, 야자시(夜子時) 적용 여부는 학파에 따라 다릅니다.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="footer">
        命理院 © 2026 · 전통 명리학을 현대 기술로 ·
        본 결과는 학술·참고 목적이며 법적 효력이 없습니다.
    </div>
    """,
    unsafe_allow_html=True,
)
