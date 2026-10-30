# Referências históricas — não executar como build integrado

`artisan-s10/` preserva 68 arquivos textuais de `platform/exynos9820` e
`target/beyond2lte` da ArtisanROM histórica. Os arquivos mantêm conteúdo e
avisos originais. A licença original está em `artisan-s10/LICENSE`.

Origem: ArtisanROM-archive/ArtisanROM_old
Commit: 5638a7f66cdf8bc9dd43f087a96f7dfa4f9e6954

O inventário `manifests/artisan-s10-files.json` lista todos os 251 arquivos
nessas duas árvores, incluindo binários NÃO importados, com Git blob ID e
size. `scripts/verify_reference.py` verifica a integridade dos textos.
Git blob SHA-1 identifica conteúdo upstream; não equivale a assinatura do autor.

Esses scripts usam a API de build antiga, dependências externas e firmware.
Ainda NÃO são módulos compatíveis com a UN1CA seventeen. Os patches podem
fazer mudanças destrutivas em um workdir: não execute diretamente no host.
O kernel histórico busca branch móvel e baixa toolchain de outro host;
substituir por referências fixas faz parte da migração ainda pendente.
