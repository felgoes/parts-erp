"""Contrato publicado: o caminho que a tela chama precisa existir no app.

Ao dividir as rotas de contas a pagar por assunto, o roteador de entrada ganhou um prefixo que os
módulos por assunto já traziam: as rotas foram para /payables/payables e a tela ficou em 404 sem
nenhum teste reclamar — os testes chamam as funções de rota direto, nunca o caminho HTTP. Este
teste olha o contrato que o app publica.
"""

from app.main import app


def _paths() -> set[str]:
    return set(app.openapi()["paths"])


def test_contas_a_pagar_publica_um_caminho_so() -> None:
    assert {
        "/api/v1/payables",
        "/api/v1/payables/report",
        "/api/v1/payables/export.csv",
        "/api/v1/payables/{payable_id}",
        "/api/v1/payables/{payable_id}/payments",
    } <= _paths()


def test_nenhuma_rota_repete_segmento_no_caminho() -> None:
    repetidas = []
    for path in sorted(_paths()):
        partes = [parte for parte in path.strip("/").split("/") if parte]
        if any(anterior == atual for anterior, atual in zip(partes, partes[1:])):
            repetidas.append(path)
    assert repetidas == []
