function handler(event) {
  var request = event.request;
  var host = request.headers.host && request.headers.host.value.toLowerCase();

  if (host === 'humbugg.com') {
    return request;
  }

  var query = request.rawQueryString();
  var location = 'https://humbugg.com' + request.uri;
  if (query !== undefined) {
    location += '?' + query;
  }

  return {
    statusCode: 308,
    statusDescription: 'Permanent Redirect',
    headers: {
      location: { value: location },
      'cache-control': { value: 'public, max-age=86400' },
    },
  };
}
