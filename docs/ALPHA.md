# Build experimental alpha1 — SM-G975F

O pipeline `.github/workflows/alpha.yml` instala dependências em Ubuntu 22.04,
monta a base completa, inicializa submódulos fixados, compila ferramentas e
chama o `make_rom.sh` original **com geração de ZIP**. Não são removidos patches
para esconder erros de aplicação.

A seleção `alpha` do wrapper é explícita; `rom` continua sendo o estágio sem
ZIP. A versão da workspace passa a `0.1.0-alpha1`, codename `Beyoud`, e continua
não oficial. Isso não certifica que o sistema doador seja One UI 9: o SDK vem
da configuração upstream e ainda precisa ser confrontado com o firmware real.

## Como acompanhar

Tentativa iniciada nesta etapa:
https://github.com/juliermeleal55-stack/ArtisanRom_Beyoud/actions/runs/41152256479

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
