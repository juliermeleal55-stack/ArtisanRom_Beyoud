# Revisão cruzada de fontes — 2026-11-05

Inventários recursivos retornados sem truncamento, em commits fixados. Arquivo
`manifests/cross-audit.json` registra contagens, módulos ativos/desativados,
blobs e evidências. A revisão semântica é focal nos contratos de configuração,
debloat e fluxo de build; NÃO é certificação de cada arquivo/binário.

| Projeto | Commit (prefixo) | Arquivos | Target S10 | Target S10+ | Uso |
|---|---|---:|---:|---:|---|
| Artisan histórica | 5638a7f66cdf | 4.987 | 12 | 12 | Nossa estrutura/build S10 |
| Artisan atual | abeb2cac4ff8 | 2.320 | 0 | 0 | Referência Exynos 990; não transplantar |
| UN1CA y2slte | 609fa7cc738e | 2.670 | 0 | 0 | Configuração do doador, não HALs S10 |
| OneROM | 644f0aacc49a | 4.468 | 233 | 0 | Adaptações controladas, ver ONEROM-AUDIT |
| ExtremeROM fifteen | 2056320784b7 | 3.889 | 10 | 10 | Referência histórica, repositório arquivado |

Targets e plataforma próprios do S10 continuam separados. ExtremeROM é útil
como linhagem, mas seus targets ainda declaram API/VNDK 31 e esquema antigo;
seu filesystem erofs não deve substituir automaticamente nossa configuração
ext4. A Artisan atual não fornece configuração beyond*. A OneROM declara S24
FE e suporte S10 normal, não prova compatibilidade com nosso SM-S926B doador ou
S10+. Quatro módulos específicos e Extra Dim/kernel estão desativados upstream.
Não copiamos erros ignorados de HEX_PATCH para fazer a compilação prosseguir.

## Debloat e patches

Preservadas listas históricas, em vez de remover componentes grandes às cegas.
Nova validação é aplicada sobre as listas EFETIVAS após carregar configurações
ROM/plataforma/aparelho: registra plano único, bloqueia traversal/globs e
remoção de componentes críticos explicitamente protegidos. O teste da lista
histórica com eSIM fonte/sem eSIM alvo passa. Isso não resolve automaticamente
todas as dependências de apps do doador; deve-se verificar firmware/APKs reais.

Patches de HALs, SELinux, VINTF, runtime32, gralloc/Mali, áudio/câmera, SDHMS e
BPF/connectividade ainda exigem validação cruzada com o SDK e binários reais.
Não foram ativados patches de outra ROM só porque o nome do aparelho coincide.

## Construção

Ver [BUILD-STAGES.md](BUILD-STAGES.md). Mudanças específicas: paralelismo
limitado, streaming tar/lz4, liberação por partição, pausa antes de empacotar,
retirement verificado, captura de propriedades que o ZIP precisava, prova de
outputs e logs de recursos. A toolchain transitiva do kernel ainda depende de
servidor externo; pin do código principal não fixa todos os downloads.

O link oneui85-lab foi usado APENAS como referência da organização em etapas.
Nenhum de seus componentes está incorporado à base. Não mudamos o doador para
S23 FE nem S24 FE. Não há split do ZIP em três partes nem release automática.

## Critérios ainda NÃO atendidos

- Extração completa com integridade e SDK/layout reais confirmados nesta versão;
- Aplicação de todos os patches em APKs/JARs reais sem falhas;
- Kernel/toolchain transitiva compilados e imagens verificadas;
- Pico máximo de disco/RAM medido no runner com este fluxo;
- ZIP completo aprovado pelo coletor e compatibilidade física de partições;
- Boot e testes de tela, toque, modem, câmera, áudio, USB, criptografia/SELinux.

Os perfis permanecem bloqueados/não validados. Testes locais e hash de fonte
não autorizam afirmar “100% funcional”. Licenças/atribuições originais são
mantidas; regras adicionais de branding/distribuição upstream precisam ser
respeitadas antes de qualquer publicação de binários.
