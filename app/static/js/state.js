/* ===== Application State Management ===== */
const AppState = {
    // Current page
    currentPage: 'chat',

    // API config
    config: {
        provider: 'ollama',
        ollama_host: 'http://127.0.0.1',
        ollama_port: 11434,
        deepseek_api_key: '',
        deepseek_base_url: 'https://api.deepseek.com',
        default_model: '',
    },

    // Models
    models: [],

    // Chat state
    currentSessionId: null,
    currentSession: null,
    mode: 'theory',          // 'theory' or 'chart'
    chartType: 'ziwei',      // 'ziwei' or 'shishen'
    currentPerson: null,     // person identifier

    // Chart data
    ziweiData: null,
    shishenData: null,

    // Context tags (selected palace/star/stem)
    selectedContext: {},

    // UI state
    sidebarCollapsed: false,
    isStreaming: false,
    currentAbortController: null,
};

/* State change subscribers */
const _subscribers = {};

function subscribe(event, callback) {
    if (!_subscribers[event]) _subscribers[event] = [];
    _subscribers[event].push(callback);
}

function emit(event, data) {
    if (_subscribers[event]) {
        _subscribers[event].forEach(cb => cb(data));
    }
}
