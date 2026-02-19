const CACHE_NAME = 'shahin-app-v1';

// Recursos mínimos para o aplicativo iniciar mais rápido
const ASSETS_TO_CACHE = [
    '/',
    '/static/manifest.json'
];

// Instalação do Motor no telemóvel
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[Shahin App] Service Worker Instalado e Cache Criado.');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

// Ativação e limpeza de versões antigas do App
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[Shahin App] Limpando versão antiga do cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// Estratégia de Rede (Network First): Como é um sistema de gestão ao vivo, 
// o app vai sempre tentar buscar os dados mais recentes do servidor primeiro.
self.addEventListener('fetch', (event) => {
    // Ignora requisições que não sejam GET (como envio de atestados ou ponto)
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request).catch(() => {
            // Se o telemóvel estiver sem internet (offline), tenta carregar a página do cache
            return caches.match(event.request);
        })
    );
});

