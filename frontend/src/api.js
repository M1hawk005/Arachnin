const API_ROOT = import.meta.env.VITE_API_URL || '/api/v1';

async function request(path, options) {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message = typeof detail === 'string'
      ? detail
      : detail?.message || 'The request could not be completed.';
    const error = new Error(message);
    error.code = detail?.code;
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export const ingestionApi = {
  create(payload) {
    return request('/ingestions', { method: 'POST', body: JSON.stringify(payload) });
  },
  status(jobId) {
    return request(`/ingestions/${jobId}`);
  },
  result(jobId) {
    return request(`/ingestions/${jobId}/result`);
  },
  recent(limit = 8) {
    return request(`/ingestions?limit=${limit}`);
  },
};
