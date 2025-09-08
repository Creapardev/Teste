// Variáveis globais
let progressInterval;
let intervalId = null;
let intervalIdMaps = null;

// Sistema de Abas
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTab = button.getAttribute('data-tab');
            
            // Remove active class from all buttons and contents
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked button and corresponding content
            button.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });
    
    // Activate first tab by default
    if (tabButtons.length > 0) {
        tabButtons[0].click();
    }
}

// Inicialização quando a página carrega
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tab system
    initTabs();
    
    // Event listener para o formulário principal
    const form = document.getElementById('scraper-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            startScraping();
        });
    }
    
    // Event listener para o formulário do Google Maps
    const mapsForm = document.getElementById('maps-form');
    if (mapsForm) {
        mapsForm.addEventListener('submit', function(e) {
            e.preventDefault();
            startGoogleMapsSearch();
        });
    }
});

// Função para iniciar scraping principal
function startScraping() {
    const url = document.getElementById('url').value;
    const maxPages = document.getElementById('max-pages').value;
    const delay = document.getElementById('delay').value;
    const nameSelector = document.getElementById('name-selector').value;
    const phoneSelector = document.getElementById('phone-selector').value;
    
    if (!url) {
        alert('Por favor, insira uma URL.');
        return;
    }
    
    // Mostrar progresso
    const progress = document.getElementById('progress');
    const statistics = document.getElementById('statistics');
    const results = document.getElementById('results');
    const download = document.getElementById('download');
    
    if (progress) progress.style.display = 'block';
    if (statistics) statistics.style.display = 'none';
    if (results) results.style.display = 'none';
    if (download) download.style.display = 'none';
    
    // Desabilitar botão
    const btn = document.getElementById('btn-scrape');
    btn.disabled = true;
    btn.textContent = '🔄 Fazendo Scraping...';
    
    // Iniciar scraping
    fetch('/scrape', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            url: url,
            max_pages: parseInt(maxPages),
            delay: parseInt(delay),
            name_selector: nameSelector,
            phone_selector: phoneSelector
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            monitorProgress();
        } else {
            showError(data.message || 'Erro ao iniciar scraping');
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        showError('Erro de conexão');
    });
}

// Função para monitorar progresso do scraping principal
function monitorProgress() {
    progressInterval = setInterval(() => {
        fetch('/progress')
        .then(response => response.json())
        .then(data => {
            updateProgress(data);
            
            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(progressInterval);
                
                if (data.status === 'completed') {
                    loadResults();
                } else {
                    showError(data.message || 'Erro durante o scraping');
                }
                
                // Reabilitar botão
                const btn = document.getElementById('btn-scrape');
                btn.disabled = false;
                btn.textContent = '🚀 Iniciar Scraping';
            }
        })
        .catch(error => {
            console.error('Erro ao verificar progresso:', error);
            clearInterval(progressInterval);
            showError('Erro de conexão');
            
            // Reabilitar botão
            const btn = document.getElementById('btn-scrape');
            btn.disabled = false;
            btn.textContent = '🚀 Iniciar Scraping';
        });
    }, 1000);
}

// Função para atualizar progresso
function updateProgress(data) {
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const progressPercent = document.getElementById('progress-percent');
    
    const percentage = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
    
    if (progressFill) progressFill.style.width = percentage + '%';
    if (progressText) progressText.textContent = data.message || 'Processando...';
    if (progressPercent) progressPercent.textContent = percentage + '%';
    
    // Mostrar estatísticas se disponíveis
    if (data.total > 0) {
        const statistics = document.getElementById('statistics');
        const totalConsultores = document.getElementById('total-consultores');
        const paginasProcessadas = document.getElementById('paginas-processadas');
        const statusScraping = document.getElementById('status-scraping');
        
        if (statistics) statistics.style.display = 'block';
        if (totalConsultores) totalConsultores.textContent = data.current;
        if (paginasProcessadas) paginasProcessadas.textContent = data.current;
        if (statusScraping) statusScraping.textContent = data.status === 'running' ? 'Em andamento' : 'Concluído';
    }
}

// Função para carregar resultados
function loadResults() {
    fetch('/results')
    .then(response => response.json())
    .then(data => {
        if (data.success && data.data.length > 0) {
            displayResults(data.data);
            const download = document.getElementById('download');
            if (download) download.style.display = 'block';
        } else {
            showError('Nenhum dado encontrado');
        }
    })
    .catch(error => {
        console.error('Erro ao carregar resultados:', error);
        showError('Erro ao carregar resultados');
    });
}

// Função para exibir resultados
function displayResults(data) {
    const resultsDiv = document.getElementById('results-table');
    
    if (data.length === 0) {
        resultsDiv.innerHTML = '<p class="no-results">Nenhum consultor encontrado.</p>';
        return;
    }
    
    let html = `
        <table class="results-table">
            <thead>
                <tr>
                    <th>Nome</th>
                    <th>Telefone</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    data.forEach(item => {
        html += `
            <tr>
                <td>${item.nome || 'N/A'}</td>
                <td>${item.telefone || 'N/A'}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    resultsDiv.innerHTML = html;
    const results = document.getElementById('results');
    if (results) results.style.display = 'block';
}

// Função para mostrar erro
function showError(message) {
    const progressDiv = document.getElementById('progress');
    progressDiv.innerHTML = `<div class="error-message">❌ ${message}</div>`;
    
    // Esconder outras seções
    const statistics = document.getElementById('statistics');
    const results = document.getElementById('results');
    const download = document.getElementById('download');
    
    if (statistics) statistics.style.display = 'none';
    if (results) results.style.display = 'none';
    if (download) download.style.display = 'none';
}

// Função para buscar dados
function searchData() {
    const searchTerm = document.getElementById('search-input').value;
    
    if (!searchTerm.trim()) {
        alert('Por favor, digite um termo de busca.');
        return;
    }
    
    fetch('/search_data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            search_term: searchTerm
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            displaySearchResults(data.results);
        } else {
            document.getElementById('search-results').innerHTML = `<div class="error-message">${data.message}</div>`;
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        document.getElementById('search-results').innerHTML = '<div class="error-message">Erro ao buscar dados</div>';
    });
}

// Função para exibir resultados da busca
function displaySearchResults(results) {
    const resultsDiv = document.getElementById('search-results');
    
    if (results.length === 0) {
        resultsDiv.innerHTML = '<div class="no-results">Nenhum resultado encontrado.</div>';
        return;
    }
    
    let html = `
        <h4>Resultados da Busca (${results.length} encontrado(s)):</h4>
        <table class="results-table">
            <thead>
                <tr>
                    <th>Nome</th>
                    <th>Telefone</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    results.forEach(item => {
        html += `
            <tr>
                <td>${item.nome || 'N/A'}</td>
                <td>${item.telefone || 'N/A'}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    resultsDiv.innerHTML = html;
}

// Função para limpar busca
function clearSearch() {
    document.getElementById('search-input').value = '';
    document.getElementById('search-results').innerHTML = '';
}

// Função para limpar duplicatas
function cleanDuplicates() {
    if (!confirm('Tem certeza que deseja limpar as duplicatas? Esta ação criará um backup do arquivo original.')) {
        return;
    }
    
    fetch('/clean_duplicates', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`Duplicatas removidas com sucesso!\n\nEstatísticas:\n- Registros originais: ${data.stats.original_count}\n- Duplicatas removidas: ${data.stats.duplicates_removed}\n- Registros finais: ${data.stats.final_count}\n\nBackup salvo em: ${data.stats.backup_file}`);
        } else {
            alert(`Erro ao limpar duplicatas: ${data.message}`);
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        alert('Erro ao limpar duplicatas');
    });
}

// Google Maps functionality
function startGoogleMapsSearch() {
    const termoBusca = document.getElementById('termo-busca').value;
    const maxResultados = document.getElementById('max-resultados-maps').value;
    
    if (!termoBusca.trim()) {
        alert('Por favor, digite um termo de busca.');
        return;
    }
    
    // Mostrar progresso e esconder outras seções
    const progressMaps = document.getElementById('progress-maps');
    const statisticsMaps = document.getElementById('statistics-maps');
    const resultsMaps = document.getElementById('results-maps');
    const downloadMaps = document.getElementById('download-maps');
    
    if (progressMaps) progressMaps.style.display = 'block';
    if (statisticsMaps) statisticsMaps.style.display = 'none';
    if (resultsMaps) resultsMaps.style.display = 'none';
    if (downloadMaps) downloadMaps.style.display = 'none';
    
    // Desabilitar botão
    const btnMaps = document.getElementById('btn-maps');
    btnMaps.disabled = true;
    btnMaps.textContent = '🔄 Buscando...';
    
    // Iniciar busca
    fetch('/scrape_maps', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            termo_busca: termoBusca,
            max_resultados: parseInt(maxResultados)
        })
    })
    .then(response => response.json())
    .then(data => {

        console.log(data.results)
        if (data.success) {
            monitorMapsProgress();
        } else {
            showMapsError(data.message || 'Erro ao iniciar busca');
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        showMapsError('Erro de conexão');
    });
}

function monitorMapsProgress() {
    intervalIdMaps = setInterval(() => {
        fetch('/progress_maps')
        .then(response => response.json())
        .then(data => {
            updateMapsProgress(data);
            
            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(intervalIdMaps);
                
                if (data.status === 'completed') {
                    loadMapsResults();
                } else {
                    showMapsError(data.message || 'Erro durante a busca');
                }
                
                // Reabilitar botão
                const btnMaps = document.getElementById('btn-maps');
                if (btnMaps) {
                    btnMaps.disabled = false;
                    btnMaps.textContent = '🚀 Buscar no Google Maps';
                }
            }
        })
        .catch(error => {
            console.error('Erro ao verificar progresso:', error);
            clearInterval(intervalIdMaps);
            showMapsError('Erro de conexão');
            
            // Reabilitar botão
            const btnMaps = document.getElementById('btn-maps');
            if (btnMaps) {
                btnMaps.disabled = false;
                btnMaps.textContent = '🚀 Buscar no Google Maps';
            }
        });
    }, 1000);
}

function updateMapsProgress(data) {
    const progressFill = document.getElementById('progress-fill-maps');
    const progressText = document.getElementById('progress-text-maps');
    const progressPercent = document.getElementById('progress-percent-maps');
    
    console.log(data)

    const percentage = data.total > 0 ? Math.round((data.results_count / data.total) * 100) : 0;
    
    if (progressFill) progressFill.style.width = percentage + '%';
    if (progressText) progressText.textContent = data.message || 'Processando...';
    if (progressPercent) progressPercent.textContent = percentage + '%';
    
    // Mostrar estatísticas se disponíveis
    if (data.total > 0) {
        const statisticsMaps = document.getElementById('statistics-maps');
        const totalEstabelecimentos = document.getElementById('total-estabelecimentos');
        const statusBuscaMaps = document.getElementById('status-busca-maps');
        
        if (statisticsMaps) statisticsMaps.style.display = 'block';
        if (totalEstabelecimentos) totalEstabelecimentos.textContent = data.results_count;
        if (statusBuscaMaps) statusBuscaMaps.textContent = data.status === 'running' ? 'Em andamento' : 'Concluído';
    }
}

function loadMapsResults() {
    fetch('/results_maps')
    .then(response => response.json())
    .then(data => {
        console.log(data.count)
        console.log(data)
        if (data.count > 0) {
            displayMapsResults(data);
            const downloadMaps = document.getElementById('download-maps');
            if (downloadMaps) downloadMaps.style.display = 'block';
        } else {
            showMapsError('Nenhum estabelecimento encontrado');
        }
    })
    .catch(error => {
        console.error('Erro ao carregar resultados:', error);
        showMapsError('Erro ao carregar resultados');
    });
}

function displayMapsResults(data) {
    const resultsDiv = document.getElementById('results-table-maps');
    
    console.log(data)

    if (data.count === 0) {
        resultsDiv.innerHTML = '<p class="no-results">Nenhum estabelecimento encontrado.</p>';
        return;
    }
    
    let html = `
        <table class="results-table">
            <thead>
                <tr>
                    <th>Nome</th>
                    <th>Avaliação</th>
                    <th>Endereço</th>
                    <th>Telefone</th>
                    <th>Tipo</th>
                    <th>Horário</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    data.results.forEach(item => {
        html += `
            <tr>
                <td>${item.nome || 'N/A'}</td>
                <td>${item.avaliacao || 'N/A'}</td>
                <td>${item.endereco || 'N/A'}</td>
                <td>${item.telefone || 'N/A'}</td>
                <td>${item.tipo || 'N/A'}</td>
                <td>${item.horario || 'N/A'}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    resultsDiv.innerHTML = html;
    const resultsMaps = document.getElementById('results-maps');
    if (resultsMaps) resultsMaps.style.display = 'block';
}

function showMapsError(message) {
    const progressDiv = document.getElementById('progress-maps');
    progressDiv.innerHTML = `<div class="error-message">❌ ${message}</div>`;
    
    // Esconder outras seções
    const statisticsMaps = document.getElementById('statistics-maps');
    const resultsMaps = document.getElementById('results-maps');
    const downloadMaps = document.getElementById('download-maps');
    
    if (statisticsMaps) statisticsMaps.style.display = 'none';
    if (resultsMaps) resultsMaps.style.display = 'none';
    if (downloadMaps) downloadMaps.style.display = 'none';
}