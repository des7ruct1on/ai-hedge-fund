// Main Application Class
class StockAnalysisApp {
    constructor() {
        this.isAnalyzing = false;
        this.analysisInterval = null;
        this.websocket = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadInitialData();
        this.connectWebSocket();
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.websocket = new WebSocket(wsUrl);
        
        this.websocket.onopen = () => {
            console.log('WebSocket соединение установлено');
        };
        
        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };
        
        this.websocket.onclose = () => {
            console.log('WebSocket соединение закрыто');
            // Переподключаемся через 3 секунды
            setTimeout(() => this.connectWebSocket(), 3000);
        };
        
        this.websocket.onerror = (error) => {
            console.error('WebSocket ошибка:', error);
        };
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'status':
                this.updateStatusMessage(data.message);
                break;
            case 'agent_opinion':
                this.addAgentOpinion(data.data);
                break;
            case 'aggregated_decision':
                this.addAggregatedDecision(data.data);
                break;
            case 'risk_assessment':
                this.addRiskAssessment(data.data);
                break;
            case 'final_recommendations':
                this.showFinalRecommendations(data.data.recommendations);
                break;
            case 'error':
                this.handleError(data.message);
                break;
        }
    }

    bindEvents() {
        const startBtn = document.getElementById('startAnalysis');
        startBtn.addEventListener('click', () => this.startAnalysis());
    }

    async loadInitialData() {
        try {
            // Load portfolio data
            const portfolioResponse = await fetch('/api/portfolio');
            if (portfolioResponse.ok) {
                const portfolio = await portfolioResponse.json();
                this.renderPortfolio(portfolio);
            }

            // Load news data
            const newsResponse = await fetch('/api/news');
            if (newsResponse.ok) {
                const news = await newsResponse.json();
                this.renderNews(news);
            }
        } catch (error) {
            console.error('Error loading initial data:', error);
            // Показываем демо данные если API недоступен
            this.renderDemoData();
        }
    }

    async startAnalysis() {
        if (this.isAnalyzing) return;

        this.isAnalyzing = true;
        this.showLoadingOverlay();
        this.updateStatus('analyzing', 'Анализ в процессе...');
        
        // Очищаем предыдущие результаты
        this.clearResults();

        try {
            // Start analysis
            const response = await fetch('/api/start_analysis', { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            // Показываем секции для real-time обновлений
            this.showSection('discussionSection');
            this.showSection('riskSection');
            this.showSection('recommendationsSection');
            
        } catch (error) {
            console.error('Error starting analysis:', error);
            this.handleError('Ошибка запуска анализа: ' + error.message);
        }
    }

    startStatusPolling() {
        this.analysisInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/status');
                const status = await response.json();
                this.updateAnalysisStatus(status);
            } catch (error) {
                console.error('Error polling status:', error);
            }
        }, 1000);
    }

    updateAnalysisStatus(status) {
        switch (status.status) {
            case 'analyzing':
                this.updateProgress();
                break;
            case 'completed':
                this.handleAnalysisComplete(status);
                break;
            case 'error':
                this.handleError(status.error || 'Неизвестная ошибка');
                break;
        }
    }

    updateProgress() {
        const progressFill = document.getElementById('progressFill');
        const currentWidth = parseInt(progressFill.style.width) || 0;
        const newWidth = Math.min(currentWidth + Math.random() * 10, 90);
        progressFill.style.width = newWidth + '%';
    }

    handleAnalysisComplete(status) {
        this.isAnalyzing = false;
        clearInterval(this.analysisInterval);
        this.hideLoadingOverlay();
        this.updateStatus('completed', 'Анализ завершен');
        
        // Show all sections
        this.showSection('discussionSection');
        this.showSection('riskSection');
        this.showSection('recommendationsSection');

        // Render results
        this.renderAgentOpinions(status.agent_opinions || []);
        this.renderRiskAssessments(status.risk_assessments || []);
        this.renderFinalRecommendations(status.final_recommendations || '');

        // Scroll to results
        setTimeout(() => {
            document.getElementById('discussionSection').scrollIntoView({ 
                behavior: 'smooth' 
            });
        }, 500);
    }

    handleError(errorMessage) {
        this.isAnalyzing = false;
        clearInterval(this.analysisInterval);
        this.hideLoadingOverlay();
        this.updateStatus('error', 'Ошибка анализа');
        
        // Show error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.innerHTML = `
            <div class="section">
                <h2><i class="fas fa-exclamation-triangle"></i> Ошибка</h2>
                <p>${errorMessage}</p>
            </div>
        `;
        document.querySelector('.main-content').appendChild(errorDiv);
    }

    updateStatus(status, text) {
        const statusText = document.getElementById('statusText');
        const statusIcon = document.getElementById('statusIcon');
        
        statusText.textContent = text;
        statusIcon.className = `status-icon ${status}`;
    }

    showLoadingOverlay() {
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    hideLoadingOverlay() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showSection(sectionId) {
        const section = document.getElementById(sectionId);
        if (section) {
            section.style.display = 'block';
            section.style.animation = 'fadeInUp 0.6s ease-out';
        }
    }

    renderPortfolio(portfolio) {
        const portfolioGrid = document.getElementById('portfolioGrid');
        portfolioGrid.innerHTML = '';

        Object.entries(portfolio).forEach(([ticker, data]) => {
            const portfolioItem = document.createElement('div');
            portfolioItem.className = 'portfolio-item';
            portfolioItem.innerHTML = `
                <h3>${ticker}</h3>
                <div class="portfolio-details">
                    <span>Количество:</span>
                    <strong>${data.quantity} акций</strong>
                    <span>Средняя цена:</span>
                    <strong>${data.avg_price} ₽</strong>
                    <span>Текущая цена:</span>
                    <strong>${data.current_price} ₽</strong>
                    <span>Сектор:</span>
                    <strong>${data.sector}</strong>
                </div>
            `;
            portfolioGrid.appendChild(portfolioItem);
        });
    }

    renderNews(news) {
        const newsList = document.getElementById('newsList');
        newsList.innerHTML = '';

        news.forEach(item => {
            const newsItem = document.createElement('div');
            newsItem.className = `news-item ${item.sentiment}`;
            newsItem.innerHTML = `
                <h4>${item.title}</h4>
                <p>${item.summary}</p>
                <div class="news-meta">
                    <span>${item.ticker}</span>
                    <span>${item.date}</span>
                </div>
            `;
            newsList.appendChild(newsItem);
        });
    }

    renderAgentOpinions(opinions) {
        const discussionContainer = document.getElementById('discussionContainer');
        discussionContainer.innerHTML = '';

        // Group opinions by ticker
        const opinionsByTicker = {};
        opinions.forEach(opinion => {
            if (!opinionsByTicker[opinion.ticker]) {
                opinionsByTicker[opinion.ticker] = [];
            }
            opinionsByTicker[opinion.ticker].push(opinion);
        });

        // Render each ticker discussion
        Object.entries(opinionsByTicker).forEach(([ticker, tickerOpinions]) => {
            const tickerDiv = document.createElement('div');
            tickerDiv.className = 'discussion-ticker';
            tickerDiv.innerHTML = `
                <h3><i class="fas fa-chart-line"></i> ${ticker}</h3>
                <div class="agent-opinions">
                    ${tickerOpinions.map(opinion => this.renderAgentOpinion(opinion)).join('')}
                </div>
            `;
            discussionContainer.appendChild(tickerDiv);
        });
    }

    renderAgentOpinion(opinion) {
        const agentClass = opinion.agent_name.toLowerCase();
        const decisionClass = `decision-${opinion.action.toLowerCase()}`;
        
        // Парсим Markdown в HTML
        const reasoningHtml = marked.parse(opinion.reasoning || '');
        
        return `
            <div class="agent-opinion ${agentClass}">
                <div class="agent-header">
                    <span class="agent-name">${opinion.agent_name}</span>
                    <span class="agent-decision ${decisionClass}">${opinion.action}</span>
                </div>
                <div class="agent-reasoning">
                    ${reasoningHtml}
                </div>
                <div style="margin-top: 10px; font-size: 0.8rem; color: #999;">
                    Уверенность: ${opinion.confidence}/10
                </div>
            </div>
        `;
    }

    renderRiskAssessments(risks) {
        const riskContainer = document.getElementById('riskContainer');
        riskContainer.innerHTML = '';

        risks.forEach(risk => {
            const riskItem = document.createElement('div');
            riskItem.className = 'risk-item';
            riskItem.innerHTML = `
                <h4>${risk.ticker}</h4>
                <div class="risk-level">
                    <span>Уровень риска:</span>
                    <div class="risk-bar">
                        <div class="risk-fill" style="width: ${risk.risk_level * 10}%"></div>
                    </div>
                    <span class="risk-number">${risk.risk_level}/10</span>
                </div>
                <div class="risk-factors">
                    <strong>Факторы риска:</strong>
                    <ul>
                        ${risk.risk_factors.map(factor => `<li>${factor}</li>`).join('')}
                    </ul>
                </div>
                <div class="risk-recommendations">
                    <strong>Рекомендации:</strong>
                    <p>${risk.recommendations}</p>
                </div>
            `;
            riskContainer.appendChild(riskItem);
        });
    }

    renderFinalRecommendations(recommendations) {
        const recommendationsContainer = document.getElementById('recommendationsContainer');
        // Парсим Markdown в HTML
        const recommendationsHtml = marked.parse(recommendations || '');
        recommendationsContainer.innerHTML = `
            <div class="recommendations-content">
                ${recommendationsHtml}
            </div>
        `;
    }

    renderDemoData() {
        // Демо данные для портфеля
        const demoPortfolio = {
            "SBER": {
                "quantity": 100,
                "avg_price": 250.50,
                "current_price": 245.30,
                "sector": "Банки"
            },
            "GAZP": {
                "quantity": 50,
                "avg_price": 180.20,
                "current_price": 175.80,
                "sector": "Энергетика"
            }
        };
        this.renderPortfolio(demoPortfolio);

        // Демо данные для новостей
        const demoNews = [
            {
                "title": "Сбербанк объявил о росте прибыли",
                "summary": "Крупнейший банк России показал рост прибыли на 15%",
                "ticker": "SBER",
                "date": "2024-01-15",
                "sentiment": "positive"
            },
            {
                "title": "Газпром снижает экспортные поставки",
                "summary": "Компания сократила экспорт газа в Европу на 20%",
                "ticker": "GAZP", 
                "date": "2024-01-14",
                "sentiment": "negative"
            }
        ];
        this.renderNews(demoNews);
    }

    // Real-time update methods
    updateStatusMessage(message) {
        const statusText = document.getElementById('statusText');
        if (statusText) {
            statusText.textContent = message;
        }
        
        // Добавляем сообщение в лог
        this.addStatusLog(message);
    }

    addStatusLog(message) {
        const discussionContainer = document.getElementById('discussionContainer');
        if (discussionContainer) {
            const logDiv = document.createElement('div');
            logDiv.className = 'status-log';
            logDiv.innerHTML = `
                <div class="log-message">
                    <span class="log-time">${new Date().toLocaleTimeString()}</span>
                    <span class="log-text">${message}</span>
                </div>
            `;
            discussionContainer.appendChild(logDiv);
            discussionContainer.scrollTop = discussionContainer.scrollHeight;
        }
    }

    addAgentOpinion(opinion) {
        const discussionContainer = document.getElementById('discussionContainer');
        if (discussionContainer) {
            const opinionDiv = document.createElement('div');
            opinionDiv.className = 'agent-opinion-realtime';
            opinionDiv.innerHTML = this.renderAgentOpinion(opinion);
            discussionContainer.appendChild(opinionDiv);
            
            // Анимация появления
            opinionDiv.style.opacity = '0';
            opinionDiv.style.transform = 'translateY(20px)';
            setTimeout(() => {
                opinionDiv.style.transition = 'all 0.5s ease';
                opinionDiv.style.opacity = '1';
                opinionDiv.style.transform = 'translateY(0)';
            }, 100);
        }
    }

    addAggregatedDecision(decision) {
        // Можно добавить визуализацию агрегированных решений
        console.log('Aggregated decision:', decision);
    }

    addRiskAssessment(risk) {
        const riskContainer = document.getElementById('riskContainer');
        if (riskContainer) {
            const riskDiv = document.createElement('div');
            riskDiv.className = 'risk-item-realtime';
            riskDiv.innerHTML = `
                <h4>${risk.ticker}</h4>
                <div class="risk-level">
                    <span>Уровень риска:</span>
                    <div class="risk-bar">
                        <div class="risk-fill" style="width: ${risk.risk_level * 10}%"></div>
                    </div>
                    <span class="risk-number">${risk.risk_level}/10</span>
                </div>
                <div class="risk-factors">
                    <strong>Факторы риска:</strong>
                    <ul>
                        ${risk.risk_factors.map(factor => `<li>${factor}</li>`).join('')}
                    </ul>
                </div>
                <div class="risk-recommendations">
                    <strong>Рекомендации:</strong>
                    <p>${risk.recommendations}</p>
                </div>
            `;
            riskContainer.appendChild(riskDiv);
        }
    }

    showFinalRecommendations(recommendations) {
        const recommendationsContainer = document.getElementById('recommendationsContainer');
        if (recommendationsContainer) {
            // Парсим Markdown в HTML
            const recommendationsHtml = marked.parse(recommendations || '');
            recommendationsContainer.innerHTML = `
                <div class="recommendations-content">
                    ${recommendationsHtml}
                </div>
            `;
        }
        
        // Завершаем анализ
        this.isAnalyzing = false;
        this.hideLoadingOverlay();
        this.updateStatus('completed', 'Анализ завершен');
    }

    clearResults() {
        const discussionContainer = document.getElementById('discussionContainer');
        const riskContainer = document.getElementById('riskContainer');
        const recommendationsContainer = document.getElementById('recommendationsContainer');
        
        if (discussionContainer) discussionContainer.innerHTML = '';
        if (riskContainer) riskContainer.innerHTML = '';
        if (recommendationsContainer) recommendationsContainer.innerHTML = '';
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new StockAnalysisApp();
});

// Add some utility functions
function formatCurrency(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB'
    }).format(amount);
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('ru-RU');
}

// Add smooth scrolling for better UX
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});
