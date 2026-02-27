"""Pure-Python tdata parser — extracts auth_key and dc_id without opentele/PyQt5.

Based on https://github.com/ntqbit/tdesktop-decrypter (MIT License).
Only requires tgcrypto (already a dependency of pyrogram).
"""

import hashlib
import os
from io import BytesIO

import tgcrypto

# ── TDF file format ──────────────────────────────────────────────

TDF_MAGIC = b"TDF$"


def _parse_tdf(data: bytes) -> tuple[int, bytes]:
    """Parse raw TDF file: magic + version + payload + md5."""
    if data[:4] != TDF_MAGIC:
        raise ValueError("Не TDF файл (неверная сигнатура)")

    version = int.from_bytes(data[4:8], "little")
    payload = data[8:-16]
    stored_hash = data[-16:]

    check = (
        payload
        + len(payload).to_bytes(4, "little")
        + version.to_bytes(4, "little")
        + TDF_MAGIC
    )
    if hashlib.md5(check).digest() != stored_hash:
        raise ValueError("Контрольная сумма TDF не совпадает — файл повреждён")

    return version, payload


def _read_tdf(base_path: str, name: str) -> tuple[int, bytes]:
    """Read TDF file trying suffixes 's' then bare name."""
    for suffix in ("s", ""):
        path = os.path.join(base_path, name + suffix)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return _parse_tdf(f.read())
    raise FileNotFoundError(f"TDF файл '{name}' не найден в {base_path}")


def _read_encrypted_file(base_path: str, name: str, local_key: bytes) -> tuple[int, bytes]:
    """Read and decrypt an encrypted TDF file."""
    version, payload = _read_tdf(base_path, name)
    encrypted = _read_qt_byte_array(BytesIO(payload))
    return version, _decrypt_local(encrypted, local_key)


# ── Qt data stream helpers ───────────────────────────────────────

def _read_bytes(stream: BytesIO, size: int) -> bytes:
    b = stream.read(size)
    if len(b) != size:
        raise StopIteration()
    return b


def _read_qt_int32(stream: BytesIO) -> int:
    return int.from_bytes(_read_bytes(stream, 4), "big", signed=True)


def _read_qt_uint64(stream: BytesIO) -> int:
    return int.from_bytes(_read_bytes(stream, 8), "big", signed=False)


def _read_qt_byte_array(stream: BytesIO) -> bytes:
    length = _read_qt_int32(stream)
    if length <= 0:
        return b""
    return _read_bytes(stream, length)


# ── Crypto ───────────────────────────────────────────────────────

def _create_local_key(passcode: bytes, salt: bytes) -> bytes:
    iterations = 100_000 if passcode else 1
    password = hashlib.sha512(salt + passcode + salt).digest()
    return hashlib.pbkdf2_hmac("sha512", password, salt, iterations, 256)


def _prepare_aes(local_key: bytes, msg_key: bytes) -> tuple[bytes, bytes]:
    x = 8  # decrypt direction
    k = local_key

    sha1_a = hashlib.sha1(msg_key + k[x : x + 32]).digest()
    sha1_b = hashlib.sha1(k[x + 32 : x + 48] + msg_key + k[x + 48 : x + 64]).digest()
    sha1_c = hashlib.sha1(k[x + 64 : x + 96] + msg_key).digest()
    sha1_d = hashlib.sha1(msg_key + k[x + 96 : x + 128]).digest()

    aes_key = sha1_a[:8] + sha1_b[8:20] + sha1_c[4:16]
    aes_iv = sha1_a[8:20] + sha1_b[:8] + sha1_c[16:20] + sha1_d[:8]
    return aes_key, aes_iv


def _decrypt_local(encrypted: bytes, local_key: bytes) -> bytes:
    if len(encrypted) < 16:
        raise ValueError("Зашифрованные данные слишком коротки")

    msg_key = encrypted[:16]
    aes_key, aes_iv = _prepare_aes(local_key, msg_key)
    decrypted = tgcrypto.ige256_decrypt(encrypted[16:], aes_key, aes_iv)

    if hashlib.sha1(decrypted).digest()[:16] != msg_key:
        raise ValueError("Ошибка дешифровки — неверный ключ или повреждённые данные")

    length = int.from_bytes(decrypted[:4], "little")
    if length > len(decrypted):
        raise ValueError(f"Повреждённые данные: длина {length} > {len(decrypted)}")

    return decrypted[4 : 4 + length]


# ── Settings blocks reader (minimal) ────────────────────────────

_DBI_MTP_AUTHORIZATION = 0x4B


def _read_settings_blocks(stream: BytesIO) -> dict[int, bytes]:
    """Read settings block list, only keeping dbiMtpAuthorization."""
    blocks: dict[int, bytes] = {}
    try:
        while True:
            block_id = _read_qt_int32(stream)
            if block_id == _DBI_MTP_AUTHORIZATION:
                blocks[block_id] = _read_qt_byte_array(stream)
            elif block_id in (0x06, 0x07, 0x0A, 0x0C, 0x1D):
                # Boolean blocks: dbiAutoStart, dbiStartMinimized, etc.
                _read_qt_int32(stream)
            elif block_id == 0x0D:  # dbiLastUpdateCheck
                _read_qt_int32(stream)
            elif block_id == 0x58:  # dbiScalePercent
                _read_qt_int32(stream)
            elif block_id == 0x57:  # dbiPowerSaving
                _read_qt_int32(stream)
            elif block_id == 0x4E:  # dbiLangPackKey
                _read_qt_uint64(stream)
            elif block_id == 0x5A:  # dbiLanguagesKey
                _read_qt_uint64(stream)
            elif block_id == 0x23:  # dbiDialogLastPath
                _read_qt_byte_array(stream)  # utf8/utf16 string
            elif block_id == 0x54:  # dbiThemeKey
                _read_qt_uint64(stream)
                _read_qt_uint64(stream)
                _read_qt_int32(stream)
            elif block_id == 0x61:  # dbiBackgroundKey
                _read_qt_uint64(stream)
                _read_qt_uint64(stream)
            elif block_id == 0x55:  # dbiTileBackground
                _read_qt_int32(stream)
                _read_qt_int32(stream)
            elif block_id == 0x29:  # dbiSongVolumeOld
                _read_qt_int32(stream)
            elif block_id == 0x5E:  # dbiApplicationSettings
                _read_qt_byte_array(stream)
            elif block_id == 0x60:  # dbiFallbackProductionConfig
                _read_qt_byte_array(stream)
            elif block_id == 0x4D:  # dbiSessionSettings
                _read_qt_byte_array(stream)
            elif block_id == 0x5C:  # dbiCacheSettings
                _read_qt_byte_array(stream)
            else:
                # Unknown block — skip by reading a QByteArray
                _read_qt_byte_array(stream)
    except StopIteration:
        pass
    return blocks


# ── MTP authorization parser ────────────────────────────────────

def _parse_mtp_auth(data: bytes) -> dict:
    """Parse MTP authorization block → {user_id, dc_id, auth_key}."""
    stream = BytesIO(data)

    legacy_user_id = _read_qt_int32(stream)
    legacy_dc_id = _read_qt_int32(stream)

    if legacy_user_id == -1 and legacy_dc_id == -1:
        user_id = _read_qt_uint64(stream)
        dc_id = _read_qt_int32(stream)
    else:
        user_id = legacy_user_id
        dc_id = legacy_dc_id

    # Read auth keys: count × (dc_id + 256-byte key)
    keys = {}
    count = _read_qt_int32(stream)
    for _ in range(count):
        key_dc = _read_qt_int32(stream)
        key_data = stream.read(256)
        if len(key_data) == 256:
            keys[key_dc] = key_data

    return {"user_id": user_id, "dc_id": dc_id, "keys": keys}


# ── Naming helpers ──────────────────────────────────────────────

def _compute_dataname_key(dataname: str) -> str:
    """Compute the hex filename key from a dataname string."""
    digest = hashlib.md5(dataname.encode("utf-8")).digest()[:8]
    # Each byte → 2 hex chars reversed
    return "".join(f"{b:02X}"[::-1] for b in digest)


def _account_name(dataname: str, index: int) -> str:
    return f"{dataname}#{index + 1}" if index > 0 else dataname


# ── Public API ──────────────────────────────────────────────────

def read_tdata(tdata_path: str, passcode: str = "") -> dict:
    """Read tdata folder and extract auth credentials.

    Returns:
        dict with keys: 'user_id' (int), 'dc_id' (int),
        'auth_key' (bytes, 256 bytes for the main DC).

    Raises:
        FileNotFoundError: if key_data file is missing
        ValueError: if tdata is corrupted or encrypted with unknown passcode
    """
    # 1. Read and decrypt key_data
    _, key_data_payload = _read_tdf(tdata_path, "key_data")
    stream = BytesIO(key_data_payload)

    salt = _read_qt_byte_array(stream)
    key_encrypted = _read_qt_byte_array(stream)
    info_encrypted = _read_qt_byte_array(stream)

    passcode_key = _create_local_key(passcode.encode("utf-8"), salt)
    local_key = _decrypt_local(key_encrypted, passcode_key)
    if len(local_key) < 256:
        raise ValueError(f"Локальный ключ слишком короткий: {len(local_key)} байт")

    # 2. Get account indices
    info_data = _decrypt_local(info_encrypted, local_key)
    info_stream = BytesIO(info_data)
    count = _read_qt_int32(info_stream)
    if count <= 0:
        raise ValueError("В tdata не найдено ни одного аккаунта")

    account_index = _read_qt_int32(info_stream)

    # 3. Read account's MTP authorization
    acct_name = _account_name("data", account_index)
    dataname_key = _compute_dataname_key(acct_name)

    version, acct_data = _read_encrypted_file(tdata_path, dataname_key, local_key)
    blocks = _read_settings_blocks(BytesIO(acct_data))

    if _DBI_MTP_AUTHORIZATION not in blocks:
        raise ValueError("Блок MTP-авторизации не найден в данных аккаунта")

    mtp = _parse_mtp_auth(blocks[_DBI_MTP_AUTHORIZATION])

    dc_id = mtp["dc_id"]
    if dc_id not in mtp["keys"]:
        raise ValueError(f"Auth key для DC {dc_id} не найден")

    return {
        "user_id": mtp["user_id"],
        "dc_id": dc_id,
        "auth_key": mtp["keys"][dc_id],
    }
