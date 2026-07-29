class OritaError(Exception):
    pass

class OritaAuthError(OritaError):
    pass

class OritaNotFoundError(OritaError):
    pass

class OritaSlotUnavailableError(OritaError):
    pass
