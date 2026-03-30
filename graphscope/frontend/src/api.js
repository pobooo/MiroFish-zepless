const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed with ${response.status}`)
  }

  return response.json()
}

export function fetchHealth() {
  return request('/health')
}

export function fetchGroups() {
  return request('/groups')
}

export function fetchGraphData(groupId, maxNodes = 400, maxEdges = 800, selectionMode = 'degree_hub') {
  const params = new URLSearchParams({
    max_nodes: String(maxNodes),
    max_edges: String(maxEdges),
    selection_mode: selectionMode,
  })
  if (groupId) params.set('group_id', groupId)
  return request(`/graphs/data?${params.toString()}`)
}

export function fetchGraphMetrics(groupId, topK = 10, communityAlgorithm = 'louvain') {
  const params = new URLSearchParams()
  if (groupId) params.set('group_id', groupId)
  params.set('top_k', String(topK))
  params.set('community_algorithm', communityAlgorithm)
  return request(`/graphs/metrics?${params.toString()}`)
}

export function fetchRanking(metric, groupId, topK = 10) {
  const params = new URLSearchParams({ metric, top_k: String(topK) })
  if (groupId) params.set('group_id', groupId)
  return request(`/graphs/rankings?${params.toString()}`)
}

export function fetchRagContext(payload) {
  return request('/rag/context', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
