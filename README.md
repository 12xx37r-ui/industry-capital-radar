# Industry Capital Radar V0.4.0

시장 관심이 낮은 상태에서 기업 CAPEX·수주·고용·공식 산업통계·공급망 신호가 먼저 움직이는 산업과 상장 수혜 후보를 찾는 실험 엔진입니다.

## V0.4.0

- OpenDART: CAPEX·매출·이익·고용·수주 공시·발행주식수
- FRED: 미국 금리·물가·고용·산업생산·유동성
- ECOS: 한국 산업생산·설비투자·기업신용·수출 시계열 자동 탐색
- KOSIS: 생산·출하·재고·설비투자·산업고용 통계 자동 탐색
- 산업 공급망 전이 점수
- 근사 P/E·P/B 기반 가격 매력 점수
- 산업 선투자 TOP10 및 상장 수혜 후보 출력
- API 연결·점수 반영 상태 출력

## GitHub Secrets

- `OPENDART_API_KEY`
- `ECOS_API_KEY`
- `KOSIS_API_KEY`
- `FRED_API_KEY`

## 첫 실행

`Actions → Industry Capital Radar → Run workflow → monthly`

## 출력

- `public/industry_radar.json`
- `public/industry_detail.json`
- `public/opportunity_top10.json`
- `public/supply_chain_radar.json`
- `public/engine_status.json`
- `public/api_status.json`

## 주의

- 점수는 확률이 아닙니다.
- 기업 P/E·P/B는 OpenDART 연차자료와 최근 보조주가로 계산한 근사치입니다.
- 시장가격은 비공식 보조 소스를 사용하므로 최종 투자 전 별도 확인이 필요합니다.
