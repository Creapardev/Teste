# Webscraping Consultores - Deploy no Easypanel

Esta aplicação Flask realiza webscraping de consultores imobiliários e estabelecimentos do Google Maps.

## 🚀 Deploy no Easypanel

### Pré-requisitos
- Conta no Easypanel
- Repositório no GitHub com o código

### Configuração no Easypanel

1. **Criar Novo Serviço**
   - Acesse seu painel do Easypanel
   - Clique em "Criar Serviço" > "App"

2. **Configurar Fonte**
   - **Tipo**: GitHub
   - **Proprietário**: `[seu-usuario-github]`
   - **Repositório**: `[nome-do-repositorio]`
   - **Branch**: `main` (ou `master`)
   - **Caminho de Build**: deixe vazio (raiz do projeto)

3. **Configurações Avançadas**
   - **Método de Build**: Docker
   - **Dockerfile**: `Dockerfile` (já incluído no projeto)
   - **Porta**: `5000`

4. **Variáveis de Ambiente** (opcional)
   ```
   PORT=5000
   FLASK_ENV=production
   ```

5. **Deploy**
   - Clique em "Criar Serviço"
   - Aguarde o build e deploy automático

## 🔧 Correções Implementadas

### Problema Original
O deploy estava falhando com erro:
```
apt-key: not found
```

### Soluções Aplicadas

1. **Dockerfile Moderno**
   - Substituído `apt-key` (depreciado) por `gpg --dearmor`
   - Método moderno de instalação do Google Chrome
   - ChromeDriver configurado automaticamente

2. **Configuração Docker-Ready**
   - Chrome em modo headless
   - Configurações otimizadas para containers
   - Usuário não-root para segurança

3. **Dependencies Completas**
   - `requirements.txt` atualizado com todas as dependências
   - Versões específicas para estabilidade

4. **Flask para Produção**
   - Host `0.0.0.0` para aceitar conexões externas
   - Porta configurável via variável de ambiente
   - Debug desabilitado

## 📦 Arquivos Importantes

- `Dockerfile` - Configuração do container
- `requirements.txt` - Dependências Python
- `.dockerignore` - Arquivos excluídos do build
- `app.py` - Aplicação principal (modificada para Docker)

## 🌐 Funcionalidades

- Webscraping de consultores imobiliários
- Busca no Google Maps
- Export para CSV/Excel
- Interface web intuitiva
- Sistema de webhook
- Remoção de duplicatas

## 🔍 Monitoramento

Após o deploy, você pode:
- Acessar logs em tempo real no Easypanel
- Monitorar CPU e memória
- Configurar domínio personalizado
- Ativar SSL automático

## 🆘 Troubleshooting

Se o deploy falhar:
1. Verifique os logs no Easypanel
2. Confirme que o Dockerfile está na raiz
3. Verifique se todas as dependências estão no requirements.txt
4. Teste localmente com Docker:
   ```bash
   docker build -t webscraping .
   docker run -p 5000:5000 webscraping
   ```

## 📞 Suporte

Em caso de problemas, verifique:
- Logs do container no Easypanel
- Status do serviço
- Configurações de rede e porta