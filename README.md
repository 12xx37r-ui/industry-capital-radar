# Industry Capital Radar V0.5.0

현재는 시장 관심이 낮지만 CAPEX·수주·고용·공식 산업통계·공급망에서 자금 유입이 먼저 가속되는 산업과 국내 상장 수혜 후보를 찾는 실험 엔진입니다.

## V0.5.0 핵심 변경

- `pre_boom_pattern_score`: AI 대중화 이전과 유사한 선투자 패턴 점수
- `capital_acceleration_score`: CAPEX·수주·공식통계 가속 확인
- `attention_gap_score`: 실물자금 가속 대비 시장 관심의 괴리
- 시장 선반영 감점 강화
- 저P/B만으로 고득점하던 오류 완화 및 가치함정 위험 추가
- 1차뿐 아니라 2차 공급망 전이 탐지
- 기업별 실적 전환 확인·선반영·과잉투자 위험 표시
- FRED 최신 관측치 수집 오류 수정
- ECOS 동일 기간 다중 행 비교 오류 수정
- KOSIS 산업고용 오선택 방지
- 동일 V0.5 실행 간 점수 변화 추적

## GitHub Secrets

- `OPENDART_API_KEY`
- `ECOS_API_KEY`
- `KOSIS_API_KEY`
- `FRED_API_KEY`

## 실행

`Actions → Industry Capital Radar → Run workflow → monthly`

## 주요 출력

- `public/next_ai_candidates.json`: Tier A/B 선행 산업과 수혜기업
- `public/opportunity_top10.json`: 선투자 산업 TOP10
- `public/industry_radar.json`: 전체 산업 점수
- `public/industry_detail.json`: 산업별 근거
- `public/supply_chain_radar.json`: 1·2차 공급망 전이
- `public/engine_status.json`
- `public/api_status.json`

## 주의

- `pre_boom_pattern_score`는 백테스트로 보정된 확률이 아닙니다.
- 대표기업 표본 기반이므로 산업 전체 모집단과 다를 수 있습니다.
- P/E·P/B와 시장가격은 근사치·보조자료이며 최종 투자 판단 전 별도 확인이 필요합니다.
