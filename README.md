# Industry Capital Radar v0.1

아직 대중적 관심은 낮지만 실물자금·설비투자·수주·R&D·고용·정부예산·공급병목이 지속·가속·확산되는 산업을 조기에 탐지하기 위한 GitHub 엔진 골격입니다.

## 고정 원칙

- GitHub/Python: 수집, 정규화, 품질검사, 계산, 예측점수, JSON 출력
- Google Apps Script: JSON 조회와 시각화만 수행
- 대시보드에서 재계산하거나 임의 보정하지 않음
- 초기 출력은 `점수`이며 검증되지 않은 수치를 `확률`이라고 부르지 않음
- 데이터가 없으면 0점으로 채우지 않고 `NO_DATA`로 표시

## 실행

```bash
python -m unittest discover -s tests -v
python -m src.main --mode manual
```

결과:

- `public/industry_radar.json`
- `public/industry_detail.json`
- `public/engine_status.json`

## 현재 상태

v0.1은 전체 구조, 산업 분류, 점수 엔진, 품질게이트, JSON 계약, GAS 표시 골격까지 포함합니다. 실제 예측을 위해서는 공식 데이터 소스별 지표 매핑과 과거 데이터 적재가 필요합니다.
