<p align="center"><img src="src/warpzip/assets/app_icon_512.png" width="160" alt="WARPZIP"></p>

# WARPZIP · 워프집

워프 속도로 압축하고 푸는 **귀여운 압축 프로그램**. 귀여운 마스코트 *워피(Warpy)* 와 함께
ZIP · 7Z · TAR 계열을 만들고, RAR · ISO 등 수십 가지 형식을 열 수 있어요.

> Windows 10/11 (x64) 대상 · Python 3.10+ / PySide6 · 개발·테스트는 Linux에서도 가능

## 주요 기능

| 구분 | 내용 |
|---|---|
| **압축** | ZIP(Deflate/BZip2/LZMA) · 7Z(LZMA2) · TAR · TAR.GZ/BZ2/XZ/**ZST** |
| **풀기** | 위 형식 + GZ/BZ2/XZ/ZST 단일 파일 + (7-Zip 엔진 사용 시) RAR · ISO · CAB · WIM · ARJ · LZH · CPIO · RPM · DEB … |
| **암호화** | ZIP **AES-256**, 7Z **AES-256**(+파일 이름 숨기기). 풀 때 비밀번호 검증 후 진행 |
| **워프 모드** | JPG·MP4·ZIP처럼 이미 압축된 파일은 자동으로 *그대로 담기* → 압축 속도 대폭 향상 |
| **분할 압축** | 100MB / CD / DVD / FAT32(4GB) / 직접 지정 → `.001 .002 …` (열 때 자동으로 이어 붙임) |
| **한글 파일명 자동 복구** | 알집 등 구버전 ZIP의 CP949 / Shift-JIS / GBK / Big5 이름을 자동 인식, 수동 선택도 가능 |
| **압축 파일 탐색기** | 폴더처럼 탐색 · 검색 · 정렬 · 미리보기(텍스트/이미지) · 드래그로 꺼내기 · 더블클릭으로 열기 |
| **압축 파일 편집** | ZIP 안에 파일 추가 / 삭제 / 이름 바꾸기 (원자적 재작성, 실패해도 원본 안전) |
| **스마트 풀기** | 최상위 항목이 여러 개일 때만 폴더를 만들어 풀기 · 덮어쓰기/건너뛰기/이름 바꿔 보관/최신만 |
| **무결성 검사 · 체크섬** | CRC 검사, CRC32/MD5/SHA-1/SHA-256/SHA-512/BLAKE2 계산 및 비교 |
| **형식 변환** | 예: RAR → ZIP, 7Z → TAR.ZST |
| **윈도우 연동** | 탐색기 우클릭(압축/바로 압축/여기에 풀기/폴더로 풀기), 파일 연결, 다중 선택 합치기, 단일 인스턴스 |
| **CLI** | `wz a/x/l/t/h` — 스크립트·CI에서 사용 |
| **그 외** | 라이트/다크 테마, 한국어/English, 일시정지/취소, 속도·남은 시간, 휴지통 삭제, 포터블 모드 |

### 보안 설계

* **Zip-Slip 방어** — `..`, 절대경로, 드라이브 문자, 심볼릭 링크 탈출을 모두 차단하고 차단 목록을 사용자에게 알림
* **압축 폭탄 경고** — 비정상적으로 큰 압축비/파일 수는 풀기 전에 확인
* **디스크 공간 사전 검사**, 취소/실패 시 **임시 파일 정리** (압축은 `.warp-part` 임시 파일 → 원자적 이름 변경)
* **Mark-of-the-Web 유지** — 인터넷에서 받은 압축 파일의 출처 표시를 풀린 파일에 전파(SmartScreen 보호 유지)
* Windows 예약 이름(`CON`, `NUL`…)·금지 문자 자동 치환, 링크/장치 파일은 기본적으로 풀지 않음
* 실행 파일 포함 시 경고, 압축 파일 안에서 실행 파일 직접 열기 전 확인

## 개발 환경에서 실행

```bash
cd warpzip
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m warpzip                  # GUI
python -m warpzip a out.7z folder  # CLI (a x e l t h)
python tools/make_assets.py        # 아이콘/마스코트/ICO 재생성
pytest -q                          # 79개 테스트 (Qt는 offscreen)
```

## Windows 빌드 & 설치 프로그램

```powershell
# (선택) RAR/ISO/CAB 지원: 7-Zip의 7z.exe + 7z.dll 을 warpzip\bin\ 에 복사
.\packaging\build_windows.ps1        # PyInstaller → dist\WarpZip\{WarpZip.exe, wz.exe}
                                     # Inno Setup이 있으면 dist\WarpZip-<ver>-setup.exe 까지 생성
```

* GitHub Actions: `.github/workflows/warpzip-windows.yml` (테스트 → 빌드 → 설치 파일/포터블 zip 아티팩트, 태그 시 릴리스)
* 포터블: `dist\WarpZip` 폴더에 빈 `portable.flag` 파일을 두면 설정이 `warpzip.ini`로 같은 폴더에 저장돼요.
* 코드 서명: 상용 배포 시 EV/OV 인증서로 `WarpZip.exe`, `wz.exe`, 설치 파일에 서명하세요(워크플로의 `SIGN_*` 시크릿 자리 참고).

## 상용화 전 체크리스트

- [ ] **라이선스 확정** — 저장소 루트의 LICENSE는 템플릿(Apache-2.0)이에요. 비공개 상용 제품이면 EULA(`EULA.txt`)를 작성하고 `installer.iss`의 `LicenseFile` 주석을 해제하세요.
- [ ] `THIRD_PARTY_NOTICES.md` 검토 (특히 Qt/PySide6·py7zr **LGPL** 준수, 7-Zip **unRAR** 제한)
- [ ] 코드 서명 인증서 적용, 설치 파일 SmartScreen 평판 확보
- [ ] 회사명·저작권·AppId(GUID) 교체 (`packaging/warpzip.spec`, `installer.iss`)
- [ ] 자동 업데이트/라이선스 인증/텔레메트리가 필요하면 별도 서비스 연동 (현재 버전은 오프라인·무수집)
- [ ] Windows 11 최상위 우클릭 메뉴는 `IExplorerCommand` 확장(MSIX sparse package)이 필요 → 현재는 "더 보기 옵션" 아래에 표시

## 알려진 제한

* RAR **생성**은 지원하지 않아요(독점 포맷). 열기는 7-Zip 엔진 필요.
* ZIP 이외 형식의 *편집*(추가/삭제)은 미지원 → "형식 변환"으로 ZIP 변환 후 편집.
* ZipCrypto(구형 암호)는 읽기만, 생성은 AES-256만 지원.
* 분할 압축은 7-Zip과 동일한 `.001` 방식이며 WinZip의 `.z01` 방식은 아니에요.
* 이 저장소의 테스트는 Linux에서 실행돼요. Windows 전용 코드(레지스트리, 휴지통, MOTW)는 Windows에서 한 번 더 확인하세요.

## 폴더 구조

```
src/warpzip/core/    # GUI 없는 엔진 (읽기/쓰기/보안/인코딩/분할/편집/해시)
src/warpzip/ui/      # PySide6 UI (메인 창, 대화상자, 진행률, 테마, i18n)
src/warpzip/shell/   # 탐색기 우클릭·파일 연결 (HKCU, 관리자 권한 불필요)
src/warpzip/assets/  # 워피 마스코트, 아이콘 SVG, ICO
tools/               # 에셋 생성기 (마스코트/아이콘)
packaging/           # PyInstaller spec, Inno Setup, 빌드 스크립트
tests/               # pytest
```
