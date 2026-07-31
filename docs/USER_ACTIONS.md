# 주인님이 해야 할 일

## 지금 필요한 것

1. GitHub에 빈 저장소 `industry-capital-radar`를 만든다.
2. OpenDART 인증키를 발급받는다.
3. 한국은행 ECOS Open API 인증키를 발급받는다.
4. KOSIS OpenAPI 인증키를 발급받는다.
5. 키를 채팅에 보내지 말고 GitHub 저장소 Settings → Secrets and variables → Actions에 아래 이름으로 저장한다.
   - `OPENDART_API_KEY`
   - `ECOS_API_KEY`
   - `KOSIS_API_KEY`
6. 이 ZIP의 내용을 저장소 최상단에 업로드한다.
7. Actions 탭에서 `Industry Capital Radar`를 수동 실행한다.

## 지금 하지 않아도 되는 것

- 산업 목록 선정
- 지표 가중치 결정
- GAS에서 점수 계산
- KIPRIS Plus 유료 신청
- 별도 유료 서버 준비

## GAS 연결은 데이터 수집기가 붙은 뒤 진행

1. Apps Script 프로젝트를 만든다.
2. `gas/CODE.gs`, `gas/INDEX.html`을 복사한다.
3. Script Properties에 `RADAR_JSON_URL`을 등록한다.
4. 비공개 GitHub 저장소라면 읽기 전용 토큰을 `GITHUB_TOKEN`에 저장한다.
5. 웹 앱으로 배포한다.
