> **Fluxo atual:** consulte [BUILD-STAGES.md](BUILD-STAGES.md) e
> [CROSS-AUDIT.md](CROSS-AUDIT.md). As tentativas e comandos anteriores abaixo
> são históricos; não comprovam sucesso do fluxo atual.

# Build experimental alpha1 — SM-G975F

O pipeline `.github/workflows/alpha.yml` instala dependências em Ubuntu 24.04,
monta a base completa, inicializa submódulos fixados, compila ferramentas e
chama o `make_rom.sh` original **com geração de ZIP**. Não são removidos patches
para esconder erros de aplicação.

A seleção `alpha` do wrapper é explícita; `rom` continua sendo o estágio sem
ZIP. A versão da workspace passa a `0.1.0-alpha1`, codename `Beyoud`, e continua
não oficial. Isso não certifica que o sistema doador seja One UI 9: o SDK vem
da configuração upstream e ainda precisa ser confrontado com o firmware real.

## Como acompanhar

Tentativa com Protobuf atualizado:
https://github.com/juliermeleal55-stack/ArtisanRom_Beyoud/actions/runs/41153543455

A tentativa anterior (41152256479) chegou à compilação das ferramentas e
falhou nesse estágio, antes dos patches/firmwares da ROM. A coleta de logs
também rejeitou caminhos contendo `..`; esse problema foi corrigido. A nova
execução configura identidade Git para os `git am` de android-tools e instala
`pcre2-utils`, sem desativar patches nem suas verificações.

Não confundir execução iniciada com build concluído. O artefato de ROM só é
coletado se a compilação, montagem e verificações estruturais passarem.
Em falha, consultar `G975F-alpha-build-diagnostics` e os logs da execução.

## Artefatos previstos em sucesso

- `Beyoud-SM-G975F-0.1.0-alpha1-UNTESTED.zip`;
- `SHA256SUMS`;
- `WARNING.txt`;
- `provenance.json`.

O coletor rejeita ZIP corrompido, componentes essenciais ausentes, boot/dtbo
vazios, falta de payload system ou assertions que aceitem os modelos S20/G975N.
Essas verificações são estruturais e **não provam segurança de instalação,
compatibilidade de HALs ou boot**. Não há teste físico nesta sessão.

Não é criada release pública automaticamente. O artefato, quando existir,
fica disponível na execução por sete dias. Não usar em telefone principal.

## Uso em uma workspace local

```bash
python3 scripts/prepare_workspace.py /caminho/externo/beyoud-workspace
python3 scripts/init_workspace_dependencies.py /caminho/externo/beyoud-workspace
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace dependencies
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace alpha
python3 scripts/collect_alpha.py /caminho/externo/beyoud-workspace /caminho/externo/alpha-output
```

Não desative assertions nem ignore falhas de patches para obter um ZIP.

## Correção da segunda tentativa

A execução 41152973515 aplicou os patches de android-tools e iniciou a
compilação C/C++. Parou em `adb/proto/app_processes.proto`: o protoc do Ubuntu
22.04 não habilita campos opcionais proto3 sem flag experimental. O runner foi
atualizado para Ubuntu 24.04, cujo protobuf suporta esses campos por padrão,
em vez de remover campos ou ignorar o erro. Isso ainda é uma falha de ferramenta,
não uma evidência de compatibilidade dos patches de framework da ROM.

## Falha de download e correção do cliente FUS

A execução 41153543455 concluiu **todas as ferramentas** e parou antes da
extração/aplicação dos patches da ROM. O cliente histórico
`ExtremeXT/samloader@69ce07a4…` falhou ao calcular a assinatura do nonce Samsung
(`auth.derive_key`, `IndexError: string index out of range`). Repetir o download
onze vezes não corrigiu a incompatibilidade de autenticação.

A dependência `external/samloader` foi substituída por
`ananjaser1211/samloader@3c372007945d4f3f165433a1d5ae40523d7f68bf`, **a mesma
revisão do submódulo da UN1CA seventeen fornecida**. Ela atualiza parâmetros de
autenticação, usa sessão HTTP persistente e envia `X-FUS-Protocol-Ver: 2.0`.
Mantém a CLI `-m/-r/-i/-s download -O`, usada pelo build antigo.

O teste offline usa nonce sintético: o cliente antigo falha e o novo passa.
O workflow agora testa esse vetor e solicita um nonce real antes de tentar
baixar firmware, com limite de 120 segundos e log. Essa inicialização não
transmite IMEI nem baixa firmware. Ela não garante que o download completo,
a versão solicitada ou o restante do port funcionem.

## Status 408 na consulta do pacote — rota SmartDownload

A captura do usuário mostra `DownloadBinaryInform returned 408`: o handshake
passou, mas a API antiga `NF_DownloadBinaryInform.do` recusou a consulta do
pacote. Isso não é prova de timeout HTTP nem falha de patches. Sem a resposta
completa não se pode atribuir o status exclusivamente ao identificador, à versão
ou ao servidor.

A nova integração usa **samloader-rs**, fixado no mesmo commit selecionado pela
UN1CA seventeen (`714d22edad16038f852cfd15903e387d1cd76d9b`). Essa implementação
usa `NF_SmartDownloadGenerateNonce.do` / `NF_SmartDownloadBinaryInform.do`, com
requisição por modelo, CSC e versão, sem campo IMEI/serial. Não são gerados
identificadores e não é necessário enviar dados pessoais do aparelho.

- `build_smart_downloader.sh` compila o cliente e um exemplo de consulta de
  metadados; `--locked` mantém as dependências Cargo do upstream.
- `probe_firmware.sh` verifica **os dois** modelos/CSCs configurados antes de
  compilar as ferramentas Android. A consulta não baixa o pacote inteiro.
- `integration/samloader/compat.py` traduz a chamada do build antigo para o
  cliente novo, normalizando a versão para quatro partes. Identificadores são
  aceitos apenas por compatibilidade da CLI e nunca encaminhados.
- O patch do downloader exige versão disponível, passa a versão explicitamente,
  remove o caso especial S731B e propaga imediatamente uma falha de download.
  Continua usando a extração e verificação MD5 dos pacotes Odin originais.
- O coletor agora publica a cauda de todos os logs, inclusive `alpha-*.log`,
  em vez de omiti-lo quando existem três arquivos.

Testes locais verificam tradução de argumentos, ausência de identificadores,
normalização/rejeição de versões, falha imediata e cobertura dos logs. O patch
foi aplicado com sucesso ao arquivo real do upstream e passou em `bash -n`.
O resultado com os servidores Samsung deve ser conferido na nova execução;
os testes locais não provam disponibilidade do pacote nem boot da ROM.

Para reproduzir a ordem nova em um host com Rust/Cargo e dependências de build:

```bash
python3 scripts/prepare_workspace.py /caminho/externo/beyoud-workspace
python3 scripts/init_workspace_dependencies.py /caminho/externo/beyoud-workspace
bash scripts/build_smart_downloader.sh /caminho/externo/beyoud-workspace
bash scripts/probe_firmware.sh /caminho/externo/beyoud-workspace
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace dependencies
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace alpha
```

A ordem antiga sem construir o cliente Rust não é mais suficiente. O cliente
Python permanece no inventário histórico das ferramentas, mas não é usado para
baixar firmware na integração nova.

## Lock compartilhado e auditoria do pipeline

A consulta agora persiste as versões em `out/firmware-lock.json`. Download e
extração leem exatamente esse arquivo, sem repetir a consulta FOTA antiga.
O lock é incluído nos diagnósticos e no pacote coletado. Veja
[BUILD-AUDIT.md](BUILD-AUDIT.md) para as demais correções e pendências reais.

## Novo preparo sequencial

O make_rom gerado agora chama o orquestrador de firmware sequencial e usa
extração ZIP com recuperação progressiva de blocos no Linux. O comando de build
continua o mesmo. Consulte BUILD-AUDIT.md antes de usar a ferramenta de extração:
o ZIP de download é descartável e não pode ser reutilizado se a extração falhar.
A integridade CRC/MD5 e os marcadores de sucesso continuam exigidos.
