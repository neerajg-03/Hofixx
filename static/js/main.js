function authHeaders() {
  const t = localStorage.getItem('token');
  return t ? { 'Authorization': `Bearer ${t}` } : {};
}

function api(path, opts={}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, authHeaders(), opts.headers || {});
  return fetch(path, Object.assign({}, opts, { headers }));
}

window.HOFIX = { api, authHeaders };

