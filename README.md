# Instrumentation Image Manager

Autor: **mari-2215**

Classificador visual e renomeador seguro para fotos de instrumentação do LABOCEANO.

## Segurança primeiro

A versão padrão **NÃO acessa o servidor**.

Sem informar caminho, o programa procura uma raiz local padrão em:

```text
D:\Marina
```

Também é possível definir um caminho local diferente com a variável `IIM_SANDBOX_ROOT` ou passar um caminho explicitamente.

Além disso:

- executar o script sem argumentos equivale a `discover` e não altera arquivos;
- caminhos UNC/de rede (`\\servidor\...`) são bloqueados sem `--allow-network`;
- `apply` e `watch` são bloqueados sem `--allow-rename`;
- `Marina/` está no `.gitignore` como proteção extra se você fizer uma cópia local dentro do projeto;
- nenhuma imagem fora da hierarquia `Fotos -> Instrumentação` é elegível;
- imagens incertas ficam como `REVISAR` e não são renomeadas automaticamente.

## Hierarquia válida

Dentro da raiz escolhida, o programa procura recursivamente:

```text
qualquer pasta
└─ Fotos
   └─ qualquer profundidade
      └─ Instrumentação  (ou Instrumentacao)
         └─ imagens a analisar
```

Uma pasta `Instrumentação` que não esteja abaixo de `Fotos` é ignorada.

## Configuração recomendada no PyCharm

1. Clone/abra este repositório.
2. Crie um ambiente virtual com Python 3.11 ou 3.12.
3. Instale as dependências:

```powershell
pip install -r requirements.txt
```

4. Garanta que sua cópia local esteja em `D:\Marina`, ou passe um caminho local explicitamente.
5. Rode primeiro:

```powershell
python tools\instrumentacao_image_manager.py
```

Como `discover` é o padrão, isso apenas informa quantas pastas e imagens elegíveis encontrou.

## Classificar a cópia local

```powershell
python tools\instrumentacao_image_manager.py classify --manifest resultado_classificacao.csv
```

O backend padrão é CLIP local. Na primeira execução, o modelo pode ser baixado e depois fica em cache.

O CSV registra:

- arquivo de origem;
- classe mais provável;
- pontuação;
- segunda classe;
- margem entre as classes;
- decisão automática ou `REVISAR`;
- nome sugerido.

Nada é renomeado durante `classify`.

## Aplicar rename somente na cópia local

Depois de revisar o CSV:

```powershell
python tools\instrumentacao_image_manager.py apply --allow-rename --manifest resultado_apply.csv
```

Ou use:

```powershell
.\APLICAR_COM_CUIDADO.ps1
```

Esse script exige digitar `APLICAR` antes de continuar.

## Acesso ao servidor: sempre explícito

O caminho real é:

```text
\\LABOCEANOSERVER\laboceano\Projetos
```

Mesmo `discover` exige autorização explícita para uma raiz UNC:

```powershell
python tools\instrumentacao_image_manager.py discover "\\LABOCEANOSERVER\laboceano\Projetos" --allow-network
```

Classificação no servidor, ainda sem rename:

```powershell
python tools\instrumentacao_image_manager.py classify "\\LABOCEANOSERVER\laboceano\Projetos" --allow-network --manifest resultado_servidor.csv
```

Para renomear no servidor seriam necessárias **as duas travas**:

```powershell
python tools\instrumentacao_image_manager.py apply "\\LABOCEANOSERVER\laboceano\Projetos" --allow-network --allow-rename --manifest resultado_apply_servidor.csv
```

Não use esse último comando antes de validar extensivamente a classificação na cópia local.

## Classes

As classes ficam em `config/classes.json` e podem ser ajustadas ao vocabulário real do laboratório sem alterar o código.

## Atalhos PowerShell

```powershell
.\setup_windows.ps1
.\descobrir.ps1
.\classificar.ps1
.\APLICAR_COM_CUIDADO.ps1
```

Os três scripts operacionais acima usam a sandbox local por padrão.

## Privacidade

A classificação CLIP roda localmente. As fotos não precisam ser enviadas para uma API externa.
