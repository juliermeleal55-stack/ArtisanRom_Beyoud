# ArtisanRom Beyoud — pesquisa de port para Galaxy S10+

Objetivo: investigar um port One UI 9 para o S10+ usando o sistema da
UN1CA `seventeen` e as adaptações históricas da ArtisanROM para Exynos 9820.

**Estado: infraestrutura inicial de pesquisa. Não existe ROM compilada,
instalador ou imagem validada neste repositório. Não faça flash destes arquivos.**
Não somos uma distribuição oficial dos projetos citados.

## Primeiros comandos

Requer Python 3. Para obter referências remotas, também requer GitHub CLI (`gh`)
com acesso aos repositórios públicos.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/port.py doctor
# doctor retorna 2 enquanto o port estiver bloqueado (comportamento esperado).
python3 scripts/port.py inspect /home/user/research/beyoud-evidence
```

`inspect` baixa apenas textos das revisões fixadas; não executa scripts remotos,
não baixa firmware e não altera as referências dos projetos originais.
Não coloque downloads de firmware, imagens ou grandes árvores upstream no Git.

## Organização

- `manifests/upstreams.json`: origens e commits analisados.
- `devices/beyond2lte/port.json`: estado explícito das validações pendentes.
- `scripts/port.py`: coleta de evidências e verificação de prontidão.
- `docs/ANALISE.md`: diferenças, riscos e sequência de implementação.

Modelo informado pelo usuário: **SM-G975F (Exynos 9820)**. Firmware atual,
bootloader, recovery e layout de partições ainda não foram coletados.
**Não se aplica ao S10+ Snapdragon**.

## Fontes incorporados

`reference/artisan-s10/` contém 68 arquivos textuais históricos, sem mudanças,
com configuração de device, overlays e módulos Exynos 9820. São referências
para migração, ainda não uma árvore compilável. O inventário de 251 arquivos
registra também os binários externos não incorporados.

```bash
python3 scripts/verify_reference.py
```

A integração histórica usa ExtremeKernel; seu repositório e commit foram
fixados no manifesto. Veja `docs/BUILD-STATUS.md` para os bloqueios reais.
A GitHub Actions valida testes, integridade e sintaxe; **não compila ROM**.

## Integração candidata implementada

Agora há um preparador da árvore **completa** da ArtisanROM histórica com um
adapter para o doador configurado na UN1CA seventeen. O build continua sendo o
original do S10+. Veja [instruções e resultado real](docs/INTEGRATION.md).

```bash
python3 scripts/prepare_workspace.py /caminho/externo/beyoud-workspace
python3 scripts/init_workspace_dependencies.py /caminho/externo/beyoud-workspace
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace dependencies
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace rom
```

Configuração gerada com sucesso; a tentativa de build parou nas dependências
ausentes do host. Patches de framework e boot continuam sem validação.

## Build alpha1

O pipeline de [alpha experimental](docs/ALPHA.md) instala dependências no
GitHub Actions e tenta gerar o instalador original com versão `0.1.0-alpha1`.
Logs são preservados em falha; um ZIP só é coletado após sucesso do build e
checagens estruturais. Isso **não equivale a teste de boot no aparelho**.
