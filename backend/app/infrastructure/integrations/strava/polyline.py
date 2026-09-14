"""Decodifica o 'encoded polyline' do Google/Strava (o traçado do mapa vem
assim em `activity.map.summary_polyline`). Algoritmo padrão, sem dependência."""

from __future__ import annotations


def decode_polyline(encoded: str) -> list[list[float]]:
    """String encoded polyline -> lista de [lat, lon]. Tolerante: string vazia
    ou inválida devolve lista vazia (nunca quebra)."""

    if not encoded:

        return []

    try:

        coords: list[list[float]] = []
        index = 0
        lat = 0
        lon = 0
        length = len(encoded)

        while index < length:

            for is_lon in (False, True):

                shift = 0
                result = 0

                while True:

                    b = ord(encoded[index]) - 63
                    index += 1
                    result |= (b & 0x1F) << shift
                    shift += 5

                    if b < 0x20:

                        break

                delta = ~(result >> 1) if (result & 1) else (result >> 1)

                if is_lon:

                    lon += delta

                else:

                    lat += delta

            coords.append([lat / 1e5, lon / 1e5])

        return coords

    except (IndexError, ValueError):

        return []
