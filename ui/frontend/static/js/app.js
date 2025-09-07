const markedScript = document.createElement('script');
markedScript.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js  ';
document.head.appendChild(markedScript);

// Вебсокет соединения
let chatSocket = null;
let logSocket = null;
let loginSocket = null;
let reasoningSocket = null;

// DOM элементы
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const chatMessages = document.getElementById('chat-messages');
const logMessages = document.getElementById('log-messages');
const logLlmMessages = document.getElementById('log-llm-messages');

// Мобильные элементы рассуждений
const mobileReasoningContainer = document.getElementById('mobile-reasoning-container');
const mobileReasoningContent = document.getElementById('mobile-reasoning-content');
const mobileReasoningToggle = document.getElementById('mobile-reasoning-toggle');

// Элементы логина
const loginInput = document.getElementById('login-input');
const loginButton = document.getElementById('login-button');

// Счетчики токенов
let tokenStats = {
    totalTokens: 0,
    promptTokens: 0,
    completionTokens: 0,  // исправлено: было completeTokens
    modelName: '-'
};

const totalTokensEl = document.getElementById('total-tokens');
const promptTokensEl = document.getElementById('prompt-tokens');
const completionTokensEl = document.getElementById('completion-tokens');
const currentModelEl = document.getElementById('current-model');

// Мобильные элементы
const mobileMessageInput = document.getElementById('mobile-message-input');
const mobileSendButton = document.getElementById('mobile-send-button');
const mobileChatMessages = document.getElementById('mobile-chat-messages');

// Инициализация вебсокетов
function initWebSockets() {
    // Вебсокет для чата
    chatSocket = new WebSocket(`ws://${window.location.host}/chat`);
    
    chatSocket.onopen = function() {
        console.log('Chat WebSocket connected');
        addSystemMessage('Чат подключен');
    };
    
    chatSocket.onmessage = function(event) {
        const message = event.data;
        addChatMessage('System', message);
        addMobileChatMessage('System', message);
        
        // Завершаем рассуждение когда приходит ответ
        finishMobileReasoning();
    };
    
    chatSocket.onclose = function() {
        console.log('Chat WebSocket disconnected');
        addSystemMessage('Чат отключен');
    };
    
    chatSocket.onerror = function(error) {
        console.error('Chat WebSocket error:', error);
        addSystemMessage('Ошибка чата');
    };
    
    // Вебсокет для логов
    logSocket = new WebSocket(`ws://${window.location.host}/log`);
    
    logSocket.onopen = function() {
        console.log('Log WebSocket connected');
    };
    
    logSocket.onmessage = function(event) {
        const logEntry = event.data;
        
        // Проверяем, является ли это LLM логом
        if (logEntry.includes('(llm)')) {
            addLlmLog(logEntry);
        } else {
            addLog(logEntry);
        }
    };
    
    logSocket.onclose = function() {
        console.log('Log WebSocket disconnected');
    };
    
    logSocket.onerror = function(error) {
        console.error('Log WebSocket error:', error);
    };
    
    // Вебсокет для логина
    loginSocket = new WebSocket(`ws://${window.location.host}/login`);
    
    loginSocket.onopen = function() {
        console.log('Login WebSocket connected');
    };
    
    loginSocket.onmessage = function(event) {
        console.log('Login WebSocket message:', event.data);
    };
    
    loginSocket.onclose = function() {
        console.log('Login WebSocket disconnected');
    };
    
    loginSocket.onerror = function(error) {
        console.error('Login WebSocket error:', error);
    };
    
    // Вебсокет для рассуждений агентов
    console.log('Attempting to connect to reasoning WebSocket...');
    reasoningSocket = new WebSocket(`ws://${window.location.host}/reasoning`);
    
    reasoningSocket.onopen = function() {
        console.log('Reasoning WebSocket connected');
        addSystemMessage('Reasoning WebSocket подключен');
    };
    
    reasoningSocket.onmessage = function(event) {
        console.log('Reasoning message received:', event.data);
        const reasoningEntry = event.data;
        addMobileReasoningMessage(reasoningEntry);
    };
    
    reasoningSocket.onclose = function(event) {
        console.log('Reasoning WebSocket disconnected:', event.code, event.reason);
        addSystemMessage('Reasoning WebSocket отключен');
    };
    
    reasoningSocket.onerror = function(error) {
        console.error('Reasoning WebSocket error:', error);
        addSystemMessage('Ошибка Reasoning WebSocket');
    };
}

// Функция для форматирования Markdown
function formatMarkdown(text) {
    if (!text) return '';
    
    try {
        // Настраиваем marked для безопасного рендеринга
        marked.setOptions({
            breaks: true, // Поддержка переносов строк
            gfm: true,    // GitHub Flavored Markdown
            sanitize: false // Разрешаем HTML (но будьте осторожны)
        });
        
        return marked.parse(text);
    } catch (error) {
        console.error('Error formatting markdown:', error);
        return text; // Возвращаем исходный текст в случае ошибки
    }
}

// Функции для добавления сообщений
function addChatMessage(username, message) {
    const messageDiv = document.createElement('div');
    
    // Определяем, является ли сообщение от пользователя
    const isUserMessage = username === 'User';
    
    // Применяем соответствующие CSS классы
    if (isUserMessage) {
        messageDiv.className = 'message user-message';
    } else {
        messageDiv.className = 'message server-message';
    }
    
    // Парсим сообщение и извлекаем саджесты
    const { text, suggests } = parseMessageWithSuggests(message);
    
    // Добавляем основной текст сообщения с Markdown форматированием
    const textDiv = document.createElement('div');
    const formattedText = formatMarkdown(text);
    textDiv.innerHTML = `${formattedText}`;
    messageDiv.appendChild(textDiv);
    
    // Добавляем саджесты, если они есть (только для серверных сообщений)
    if (suggests.length > 0 && !isUserMessage) {
        const suggestsContainer = createSuggestsContainer(suggests, 'desktop');
        messageDiv.appendChild(suggestsContainer);
    }
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addMobileChatMessage(username, message) {
    const messageDiv = document.createElement('div');
    
    // Определяем, является ли сообщение от пользователя
    const isUserMessage = username === 'User';
    
    // Применяем соответствующие CSS классы для мобильной версии
    if (isUserMessage) {
        messageDiv.className = 'mobile-message user-message';
    } else {
        messageDiv.className = 'mobile-message server-message';
    }
    
    // Парсим сообщение и извлекаем саджесты
    const { text, suggests } = parseMessageWithSuggests(message);
    
    // Добавляем основной текст сообщения с Markdown форматированием
    const textDiv = document.createElement('div');
    const formattedText = formatMarkdown(text);
    textDiv.innerHTML = `${formattedText}`;
    messageDiv.appendChild(textDiv);
    
    // В мобильной версии саджесты отображаются над полем ввода, а не в сообщении
    // Но мы сохраняем их для отображения в мобильном контейнере саджестов
    
    mobileChatMessages.appendChild(messageDiv);
    mobileChatMessages.scrollTop = mobileChatMessages.scrollHeight;
    
    // Обновляем мобильные саджесты над полем ввода (только для серверных сообщений)
    if (!isUserMessage) {
        updateMobileSuggests(suggests);
    }
}

// Функция для парсинга сообщения и извлечения саджестов
function parseMessageWithSuggests(message) {
    // Ищем саджесты в квадратных скобках в конце сообщения
    const suggestMatch = message.match(/\[(.*?)\]$/);
    
    if (suggestMatch) {
        const suggestsText = suggestMatch[1];
        const suggests = suggestsText.split(',').map(s => s.trim().replace(/['"]/g, ''));
        const text = message.replace(/\[.*?\]$/, '').trim();
        return { text, suggests };
    }
    
    return { text: message, suggests: [] };
}

// Функция для создания контейнера с саджестами
function createSuggestsContainer(suggests, type) {
    const container = document.createElement('div');
    container.className = type === 'mobile' ? 'mobile-suggests-bar' : 'desktop-suggests-bar';
    
    const header = document.createElement('div');
    header.className = type === 'mobile' ? 'mobile-suggests-header' : 'desktop-suggests-header';
    header.textContent = 'Спросить ещё';
    container.appendChild(header);
    
    const suggestsContainer = document.createElement('div');
    suggestsContainer.className = 'suggested-messages-container';
    
    const suggestsList = document.createElement('div');
    suggestsList.className = 'suggested-messages';
    
    suggests.forEach(suggest => {
        const suggestItem = document.createElement('div');
        suggestItem.className = 'suggest-item';
        
        const suggestText = document.createElement('div');
        suggestText.className = 'suggest-text';
        suggestText.textContent = suggest;
        
        const suggestPlus = document.createElement('div');
        suggestPlus.className = 'suggest-plus';
        suggestPlus.textContent = '+';
        
        suggestItem.appendChild(suggestText);
        suggestItem.appendChild(suggestPlus);
        
        // Добавляем обработчик клика
        suggestItem.addEventListener('click', () => {
            sendSuggestMessage(suggest);
        });
        
        suggestsList.appendChild(suggestItem);
    });
    
    suggestsContainer.appendChild(suggestsList);
    container.appendChild(suggestsContainer);
    
    return container;
}

// Функция для отправки сообщения-саджеста
function sendSuggestMessage(suggest) {
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(suggest);
        
        // Очищаем поля ввода
        if (messageInput) messageInput.value = '';
        if (mobileMessageInput) mobileMessageInput.value = '';
        
        // Добавляем сообщение пользователя в чат
        addChatMessage('User', suggest);
        addMobileChatMessage('User', suggest);
        
        // Скрываем мобильные саджесты после отправки
        hideMobileSuggests();
    }
}

// Функция для скрытия мобильных саджестов
function hideMobileSuggests() {
    const mobileSuggestsBar = document.getElementById('mobile-suggests-bar');
    if (mobileSuggestsBar) {
        mobileSuggestsBar.classList.add('hidden');
    }
}

// Функция для обновления мобильных саджестов над полем ввода
function updateMobileSuggests(suggests) {
    const mobileSuggestsBar = document.getElementById('mobile-suggests-bar');
    
    if (!mobileSuggestsBar) {
        console.error('Mobile suggests bar not found');
        return;
    }
    
    // Очищаем существующие саджесты
    const existingSuggests = mobileSuggestsBar.querySelector('.suggested-messages');
    if (existingSuggests) {
        existingSuggests.innerHTML = '';
    }
    
    // Если саджестов нет, скрываем панель
    if (!suggests || suggests.length === 0) {
        mobileSuggestsBar.classList.add('hidden');
        return;
    }
    
    // Показываем панель
    mobileSuggestsBar.classList.remove('hidden');
    
    // Создаем новые саджесты
    suggests.forEach(suggest => {
        const suggestItem = document.createElement('div');
        suggestItem.className = 'suggest-item';
        
        const suggestText = document.createElement('div');
        suggestText.className = 'suggest-text';
        suggestText.textContent = suggest;
        
        const suggestPlus = document.createElement('div');
        suggestPlus.className = 'suggest-plus';
        suggestPlus.textContent = '+';
        
        suggestItem.appendChild(suggestText);
        suggestItem.appendChild(suggestPlus);
        
        // Добавляем обработчик клика
        suggestItem.addEventListener('click', () => {
            sendSuggestMessage(suggest);
        });
        
        existingSuggests.appendChild(suggestItem);
    });
}

function addSystemMessage(message) {
    addChatMessage('System', message);
}

function addLog(logEntry) {
    const logDiv = document.createElement('div');
    logDiv.className = 'log-entry';
    logDiv.textContent = logEntry;
    logMessages.appendChild(logDiv);
    logMessages.scrollTop = logMessages.scrollHeight;
}

function addLlmLog(logEntry) {
    const logDiv = document.createElement('div');
    logDiv.className = 'log-entry llm';
    logDiv.textContent = logEntry;
    logLlmMessages.appendChild(logDiv);
    logLlmMessages.scrollTop = logLlmMessages.scrollHeight;
    
    // Парсим LLM лог для обновления счетчика токенов
    updateTokenCounter(logEntry);
}


// Глобальная переменная для хранения текущего мобильного рассуждения
let currentMobileReasoning = null;
let isUserScrolling = false;
let scrollTimeout = null;

function addMobileReasoningMessage(reasoningEntry) {
    // Парсим сообщение рассуждения
    const parts = reasoningEntry.split(': ');
    if (parts.length >= 2) {
        const agentName = parts[0];
        const reasoning = parts.slice(1).join(': ');
        
        // Если это новый агент или новое рассуждение
        if (!currentMobileReasoning || currentMobileReasoning.agentName !== agentName) {
            // Завершаем предыдущее рассуждение если есть
            if (currentMobileReasoning) {
                finishMobileReasoning();
            }
            
            // Создаем новое рассуждение
            currentMobileReasoning = {
                agentName: agentName,
                element: null,
                text: '',
                isTyping: false
            };
            
            // Создаем элемент рассуждения
            const reasoningDiv = document.createElement('div');
            reasoningDiv.className = 'mobile-reasoning-entry';
            reasoningDiv.innerHTML = `
                <div class="mobile-reasoning-agent">${agentName}</div>
                <div class="mobile-reasoning-text"></div>
                <div class="mobile-reasoning-cursor">|</div>
            `;
            
            currentMobileReasoning.element = reasoningDiv;
            mobileReasoningContent.appendChild(reasoningDiv);
            currentMobileReasoning.isTyping = true;
            
            // Сбрасываем флаг скролла для нового сообщения
            isUserScrolling = false;
            
            // Показываем контейнер рассуждений
            showMobileReasoningContainer();
        }
        
        // Добавляем текст с эффектом печатания
        if (currentMobileReasoning.isTyping) {
            typeMobileReasoning(reasoning);
        }
    } else {
        // Если формат не стандартный, просто добавляем как есть
        if (!currentMobileReasoning) {
            currentMobileReasoning = {
                agentName: 'System',
                element: null,
                text: '',
                isTyping: false
            };
            
            const reasoningDiv = document.createElement('div');
            reasoningDiv.className = 'mobile-reasoning-entry';
            reasoningDiv.innerHTML = `
                <div class="mobile-reasoning-agent">System</div>
                <div class="mobile-reasoning-text"></div>
                <div class="mobile-reasoning-cursor">|</div>
            `;
            
            currentMobileReasoning.element = reasoningDiv;
            mobileReasoningContent.appendChild(reasoningDiv);
            currentMobileReasoning.isTyping = true;
            
            // Показываем контейнер рассуждений
            showMobileReasoningContainer();
        }
        
        if (currentMobileReasoning.isTyping) {
            typeMobileReasoning(reasoningEntry);
        }
    }
}

function typeMobileReasoning(text) {
    if (!currentMobileReasoning || !currentMobileReasoning.isTyping) return;
    
    const textElement = currentMobileReasoning.element.querySelector('.mobile-reasoning-text');
    const cursorElement = currentMobileReasoning.element.querySelector('.mobile-reasoning-cursor');
    
    // Добавляем текст по частям
    currentMobileReasoning.text += text;
    
    // Эффект печатания по символам
    let currentIndex = 0;
    const fullText = currentMobileReasoning.text;
    
    const typeInterval = setInterval(() => {
        if (currentIndex < fullText.length) {
            textElement.textContent = fullText.substring(0, currentIndex + 1);
            currentIndex++;
            
            // Прокручиваем только если пользователь не скроллит вручную
            if (!isUserScrolling) {
                mobileReasoningContent.scrollTop = mobileReasoningContent.scrollHeight;
            }
        } else {
            clearInterval(typeInterval);
        }
    }, 20); // Скорость печатания - 20ms на символ
    
    // Мигающий курсор
    if (cursorElement) {
        cursorElement.style.animation = 'blink 1s infinite';
    }
}

function finishMobileReasoning() {
    if (currentMobileReasoning && currentMobileReasoning.isTyping) {
        const cursorElement = currentMobileReasoning.element.querySelector('.mobile-reasoning-cursor');
        if (cursorElement) {
            cursorElement.style.display = 'none';
        }
        currentMobileReasoning.isTyping = false;
        currentMobileReasoning = null;
        
        // НЕ скрываем контейнер автоматически - пользователь сам управляет видимостью
    }
}

// Функции для управления контейнером рассуждений
function showMobileReasoningContainer() {
    if (mobileReasoningContainer) {
        mobileReasoningContainer.classList.remove('hidden');
    }
}

function hideMobileReasoningContainer() {
    if (mobileReasoningContainer) {
        mobileReasoningContainer.classList.add('hidden');
    }
}

function toggleMobileReasoningContainer() {
    if (mobileReasoningContainer) {
        mobileReasoningContainer.classList.toggle('hidden');
        updateReasoningToggleButton();
        
        // Если контейнер открывается, прокручиваем к нему
        if (!mobileReasoningContainer.classList.contains('hidden')) {
            mobileReasoningContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }
}

function updateReasoningToggleButton() {
    if (mobileReasoningToggle && mobileReasoningContainer) {
        const isHidden = mobileReasoningContainer.classList.contains('hidden');
        mobileReasoningToggle.textContent = isHidden ? '+' : '−';
    }
}

// Инициализация кнопки при загрузке
function initReasoningToggle() {
    if (mobileReasoningToggle && mobileReasoningContainer) {
        updateReasoningToggleButton();
    }
}

// Очистка контейнера рассуждений
function clearMobileReasoningContainer() {
    if (mobileReasoningContent) {
        mobileReasoningContent.innerHTML = '';
    }
    // Сбрасываем текущее рассуждение
    currentMobileReasoning = null;
    isUserScrolling = false;
}

// Обработчики скролла для определения ручного скролла
function setupScrollHandlers() {
    if (mobileReasoningContent) {
        mobileReasoningContent.addEventListener('scroll', function() {
            isUserScrolling = true;
            
            // Сбрасываем таймер
            if (scrollTimeout) {
                clearTimeout(scrollTimeout);
            }
            
            // Через 1 секунду после остановки скролла считаем, что пользователь закончил скроллить
            scrollTimeout = setTimeout(() => {
                isUserScrolling = false;
            }, 1000);
        });
    }
}

// Функция для обновления счетчика токенов
function updateTokenCounter(logEntry) {
    // Ищем первую { и последнюю }
    const startIndex = logEntry.indexOf('{');
    const endIndex = logEntry.lastIndexOf('}');

    // Проверяем, что обе скобки найдены и в правильном порядке
    if (startIndex !== -1 && endIndex !== -1 && endIndex > startIndex) {
        const jsonString = logEntry.substring(startIndex, endIndex + 1);

        try {
            const parsed = JSON.parse(jsonString);

            // Обновляем статистику только если есть нужные поля
            if (parsed.model_name !== undefined) {
                tokenStats.modelName = parsed.model_name;
            }
            if (parsed.prompt_tokens !== undefined) {
                tokenStats.promptTokens = parsed.prompt_tokens;
            }
            if (parsed.completion_tokens !== undefined) {
                tokenStats.completionTokens = parsed.completion_tokens;
            }
            if (parsed.total_tokens !== undefined) {
                tokenStats.totalTokens += parsed.total_tokens;  // суммируем
            }

            updateStatsDisplay();
        } catch (e) {
            console.warn('Invalid JSON in log entry:', jsonString, e);
        }
    }
}

function updateStatsDisplay() {
    totalTokensEl.textContent = tokenStats.totalTokens.toLocaleString();
    promptTokensEl.textContent = tokenStats.promptTokens.toLocaleString();
    completionTokensEl.textContent = tokenStats.completionTokens.toLocaleString();
    currentModelEl.textContent = tokenStats.modelName;
}

// Функция отправки сообщения
function sendMessage() {
    const message = messageInput.value.trim();
    if (message && chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        // Сначала отображаем сообщение пользователя в чате
        addChatMessage('User', message);
        addMobileChatMessage('User', message);
        
        // Очищаем старые рассуждения и показываем контейнер
        clearMobileReasoningContainer();
        showMobileReasoningContainer();
        
        // Затем отправляем через вебсокет
        chatSocket.send(message);
        messageInput.value = '';
    }
}

// Функция отправки логина
function sendLogin() {
    const login = loginInput.value.trim();
    if (login && loginSocket && loginSocket.readyState === WebSocket.OPEN) {
        loginSocket.send(login);
        console.log('Отправлен логин:', login);
        loginInput.value = '';
    }
}

function sendMobileMessage() {
    const message = mobileMessageInput.value.trim();
    if (message && chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        // Сначала отображаем сообщение пользователя в чате
        addChatMessage('User', message);
        addMobileChatMessage('User', message);
        
        // Очищаем старые рассуждения и показываем контейнер
        clearMobileReasoningContainer();
        showMobileReasoningContainer();
        
        // Затем отправляем через вебсокет
        chatSocket.send(message);
        mobileMessageInput.value = '';
    }
}

// Обработчики событий
function setupEventListeners() {
    // Десктопные элементы
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    
    // Элементы логина
    loginButton.addEventListener('click', sendLogin);
    loginInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendLogin();
        }
    });
    
    // Мобильные элементы
    mobileSendButton.addEventListener('click', sendMobileMessage);
    mobileMessageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMobileMessage();
        }
    });
    
    // Обработчик для переключения контейнера рассуждений
    if (mobileReasoningToggle) {
        mobileReasoningToggle.addEventListener('click', toggleMobileReasoningContainer);
    }
    
    // Обработчик для клика по заголовку рассуждений
    if (mobileReasoningContainer) {
        const header = mobileReasoningContainer.querySelector('.mobile-reasoning-header');
        if (header) {
            header.addEventListener('click', toggleMobileReasoningContainer);
        }
    }
    
    // Мобильный переключатель
    const mobileToggle = document.getElementById('mobile-toggle');
    const iphoneContainer = document.getElementById('iphone-container');
    if (mobileToggle && iphoneContainer) {
        mobileToggle.addEventListener('click', function() {
            iphoneContainer.classList.toggle('hidden');
        });
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    initWebSockets();
    setupEventListeners();
    
    // Инициализируем отображение токенов
    updateStatsDisplay();
    
    // Инициализируем кнопку рассуждений
    initReasoningToggle();
    
    // Инициализируем обработчики скролла
    setupScrollHandlers();
    
    // Добавляем начальное сообщение
    setTimeout(() => {
        addSystemMessage('Добро пожаловать! Можете общаться');
    }, 1000);
});