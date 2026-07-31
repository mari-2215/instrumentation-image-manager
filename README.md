# Instrumentation Image Manager

Autor: **mari-2215**

Classificador/renomeador visual para as fotos de instrumentação do LABOCEANO.

## Regra de escopo

O programa parte de:

```text
\\LABOCEANOSERVER\laboceano\Projetos
```

e aplica **obrigatoriamente** a descoberta em duas etapas:

```text
Projetos
└─ qualquer projeto / qualquer profundidade
   └─ Fotos
      └─ qualquer subpasta / qualquer profundidade
         └─ Instrumentação  (ou Instrumentacao)
            └─ imagens a analisar
```

`Instrumentação` fora de `Fotos` é ignorada. Uma imagem diretamente em `Fotos` também é ignorada.

## O que mudou nesta versão

Agora o programa **abre e processa visualmente as imagens**. O backend padrão é CLIP local, usando classificação zero-shot. As classes ficam em `config/classes.json` e podem ser adaptadas ao vocabulário do laboratório sem alterar o código.

Para cada imagem o programa registra:

- classe mais provável;
- pontuação da 1ª classe;
- 2ª classe;
- margem entre as duas;
- decisão automática ou `REVISAR`;
- nome sugerido.

Imagens com baixa pontuação, pouca margem ou classe `outro` ficam como `REVISAR` e **não são renomeadas automaticamente**.

## Instalação no Windows

Recomendado: Python 3.11 ou 3.12, em um ambiente virtual.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

O `torch` pode precisar ser instalado separadamente conforme CPU/GPU do computador. Depois disso, o modelo CLIP é baixado na primeira classificação e fica em cache local.

## 1. Descobrir sem carregar IA

```powershell
py tools\instrumentacao_image_manager.py discover "\\LABOCEANOSERVER\laboceano\Projetos"
```

Esse comando só mostra quantas pastas `Fotos`, `Instrumentação` válidas e imagens elegíveis foram encontradas. Não altera nada e não carrega o modelo.

## 2. Classificar sem renomear

```powershell
py tools\instrumentacao_image_manager.py classify "\\LABOCEANOSERVER\laboceano\Projetos" --manifest resultado.csv
```

Também é aceito `scan` como sinônimo prático de classificação em dry-run.

O arquivo `resultado.csv` deve ser revisado antes do primeiro `apply`.

## 3. Renomear somente as classificações confiáveis

```powershell
py tools\instrumentacao_image_manager.py apply "\\LABOCEANOSERVER\laboceano\Projetos" --manifest resultado_apply.csv
```

Padrão de nome:

```text
{class}_{inspection}_{AAAAMMDD}_{HHMMSS}_{sequencia}.ext
```

Exemplo:

```text
IMG_4832.JPG
-> sensor_pod_20260731_142201_001.jpg
```

O programa **não move arquivos de pasta**. O rename é feito somente no mesmo diretório da imagem.

## 4. Monitorar novas imagens

```powershell
py tools\instrumentacao_image_manager.py watch "\\LABOCEANOSERVER\laboceano\Projetos" --manifest novas_imagens.csv
```

O `watch` tira um snapshot ao iniciar e ignora as fotos já existentes. Uma nova cópia só é processada depois de tamanho e `mtime` ficarem estáveis por alguns segundos.

## Classes

Edite `config/classes.json`. A versão inicial possui:

- `sensor`
- `aquisicao_dados`
- `instrumento_medicao`
- `controlador_eletronica`
- `energia_alimentacao`
- `cabos_conectores`
- `atuador_motor`
- `montagem_instrumentacao`
- `setup_ensaio`
- `identificacao_documentacao`
- `outro`

Quanto mais as descrições refletirem as fotos reais do LABOCEANO, melhor será a separação entre classes.

## Limites de confiança

Padrões iniciais:

```text
--min-score  0.35
--min-margin 0.08
```

Esses valores **não devem ser tratados como calibrados** antes de testar com fotos reais. A recomendação é rodar `classify`, conferir o CSV e só depois ajustar os limites.

## Privacidade

O backend CLIP roda localmente. As imagens não precisam ser enviadas a uma API externa.

## Atalhos PowerShell incluídos

Na raiz do repositório:

```powershell
.\setup_windows.ps1
.\descobrir.ps1
.\classificar.ps1
```

O script `APLICAR_COM_CUIDADO.ps1` exige digitar literalmente `APLICAR` antes de executar renames.
