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

// ============================================================================
// FASE 2: O CARTEIRO INVISÍVEL (MOTOR DE NOTIFICAÇÕES PUSH)
// ============================================================================

// 1. À ESCUTA: Recebendo a notificação disparada pelo servidor Python
self.addEventListener('push', function(event) {
    console.log('[Shahin App] Push Message recebida!');
    
    // Dados padrão caso algo falhe
    let data = { 
        title: 'Shahin Gestão', 
        body: 'Você tem uma nova notificação do RH.', 
        url: '/' 
    };
    
    // Tenta extrair os dados enviados pelo servidor
    if (event.data) {
        try {
            data = event.data.json(); // Se vier formatado perfeitamente (JSON)
        } catch (e) {
            data.body = event.data.text(); // Se vier apenas como texto simples
        }
    }

    // Configuração do visual e comportamento do aviso no telemóvel
    const options = {
        body: data.body,
        icon: '/static/icons/icon-192x192.png', // O ícone grande do app
        badge: '/static/icons/icon-192x192.png', // O ícone pequenino da barra de notificações (status bar)
        vibrate: [200, 100, 200, 100, 200, 100, 200], // Padrão de vibração chamativo
        data: {
            url: data.url || '/' // Guarda o link (ex: /documentos/meus-documentos) para quando o utilizador clicar
        },
        requireInteraction: true // Força a notificação a ficar no ecrã até que o utilizador a veja e feche
    };

    // Diz ao telemóvel para mostrar o alerta final!
    event.waitUntil(
        self.registration.showNotification(data.title || 'Shahin Gestão', options)
    );
});

// 2. AÇÃO: O que acontece quando o funcionário clica na notificação
self.addEventListener('notificationclick', function(event) {
    console.log('[Shahin App] Utilizador clicou na notificação.');
    
    // Fecha a notificação do ecrã
    event.notification.close();

    // Recupera para qual página o RH queria enviar o funcionário
    const targetUrl = event.notification.data.url;

    // A magia de navegação:
    event.waitUntil(
        // Verifica se o Shahin Gestão já está aberto em alguma aba ou em segundo plano
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                // Se já estiver aberto, foca na tela existente e navega para a página correta
                if (client.url.includes(self.registration.scope) && 'focus' in client) {
                    client.navigate(targetUrl);
                    return client.focus();
                }
            }
            // Se o app estiver 100% fechado, abre-o diretamente na página correta
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});

