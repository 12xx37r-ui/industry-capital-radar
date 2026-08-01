function doGet() {
  return HtmlService.createTemplateFromFile('INDEX')
    .evaluate()
    .setTitle('산업 자본이동 레이더')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function fetchJson_(url, token) {
  const options = {
    muteHttpExceptions: true,
    headers: token ? { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github.raw+json' } : {}
  };
  const response = UrlFetchApp.fetch(url, options);
  const code = response.getResponseCode();
  if (code < 200 || code >= 300) throw new Error('JSON 조회 실패: HTTP ' + code + ' / ' + url);
  return JSON.parse(response.getContentText('UTF-8'));
}

function getDashboardData() {
  const props = PropertiesService.getScriptProperties();
  const radarUrl = props.getProperty('RADAR_JSON_URL');
  if (!radarUrl) throw new Error('Script Property RADAR_JSON_URL이 없습니다.');
  const token = props.getProperty('GITHUB_TOKEN');
  return {
    radar: fetchJson_(radarUrl, token),
    api: fetchJson_(props.getProperty('API_STATUS_JSON_URL') || radarUrl.replace('industry_radar.json', 'api_status.json'), token),
    top10: fetchJson_(props.getProperty('TOP10_JSON_URL') || radarUrl.replace('industry_radar.json', 'opportunity_top10.json'), token),
    nextAi: fetchJson_(props.getProperty('NEXT_AI_JSON_URL') || radarUrl.replace('industry_radar.json', 'next_ai_candidates.json'), token)
  };
}
