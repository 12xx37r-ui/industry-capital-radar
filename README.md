# Industry Capital Radar v0.2

대중적 관심이 본격화되기 전, 실물자금·설비투자·수주·고용이 가속되는 산업을 탐지하는 GitHub 엔진입니다.

## V0.2 실제 연결

- OpenDART: 상장사 고유번호, 최근 3개 사업연도 전체 재무제표, 직원현황, 최근/직전 1년 수주·시설투자 공시 건수
- 시장 보조지표: 대표기업 6개월 수익률과 거래량 가속도(비공식 보조 데이터, 실패 시 자동 제외)
- ECOS/KOSIS: 인증키 연결상태 확인. 산업별 통계표 매핑은 V0.3에서 점수에 반영

## 중요한 제한

- 현재는 한국 대표기업 표본 기반 초기 점수다.
- 산업 전체 모집단을 대표하지 않는다.
- 0~100 점수이며 백테스트로 보정된 확률이 아니다.
- 누락 지표를 0점으로 처리하지 않고 사용 가능한 지표끼리 가중치를 재정규화한다.

## 실행

```bash
python -m unittest discover -s tests -v
python -m src.main --mode manual
```

결과:

- `public/industry_radar.json`
- `public/industry_detail.json`
- `public/engine_status.json`
- `data/normalized/industry_features.csv`
- `data/snapshots/company_metrics.json`
- `data/evidence/industry_evidence.json`
