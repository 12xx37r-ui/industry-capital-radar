# Industry Capital Radar V0.3

아직 대중과 시장의 관심은 낮지만 기업의 CAPEX·수주·고용·시장 신호와 거시환경이 먼저 움직이는 산업을 탐지하는 실험 엔진입니다.

## V0.3 기능

- OpenDART 대표기업 연차 재무·직원·공시 수집
- 시장가격·거래량 보조 신호
- FRED 금리·물가·고용·산업생산·유동성 수집 및 산업별 거시 적합도 반영
- ECOS·KOSIS 연결 상태 검사
- API 상태·확인시각·갱신상태 JSON 출력
- DART 캐시 및 병렬수집으로 반복 실행시간 단축
- 중복 실행 시 이전 실행 자동 취소
- 결과는 확률이 아닌 실험 점수

## GitHub Secrets

- `OPENDART_API_KEY`
- `ECOS_API_KEY`
- `KOSIS_API_KEY`
- `FRED_API_KEY`

## 실행 모드

- `manual`: 30일 이내 DART 캐시가 있으면 캐시 사용, 시장·FRED 갱신
- `daily`: DART 캐시 사용, 시장·FRED 갱신
- `weekly`: DART 공시·시장·FRED 갱신
- `monthly`: DART 전체 재수집 + 시장·FRED 갱신

첫 실행 또는 DART 전체 갱신이 필요하면 `monthly`를 선택합니다.

## 출력

- `public/industry_radar.json`
- `public/industry_detail.json`
- `public/engine_status.json`
- `public/api_status.json`

## 한계

- 대표기업 표본 기반입니다.
- ECOS·KOSIS는 V0.3에서 연결 상태만 확인하며 산업별 세부 통계는 아직 점수에 직접 매핑되지 않습니다.
- 점수는 워크포워드 백테스트로 보정된 확률이 아닙니다.


## v0.3.1
- KOSIS 공식 `parentId` 요청변수 적용
- KOSIS 연결 재시도 및 타임아웃 강화
- HTTP 오류 로그에서 API 키 자동 마스킹
