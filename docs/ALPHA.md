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

Tentativa atual:
https://github.com/juliermeleal55-stack/ArtisanRom_Beyoud/actions/runs/41152973515

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
