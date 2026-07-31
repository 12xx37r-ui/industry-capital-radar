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
  const apiUrl = props.getProperty('API_STATUS_JSON_URL') || radarUrl.replace('industry_radar.json', 'api_status.json');
  return {
    radar: fetchJson_(radarUrl, token),
    api: fetchJson_(apiUrl, token)
  };
}
