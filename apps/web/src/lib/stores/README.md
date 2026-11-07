UI-stores zijn per shell-instance en bevatten geen gedeelde globale toestand.
Gespreksgeschiedenis gebruikt de Dexie-repository in `features/chat/` als
IndexedDB-grens; introduceer geen serveropslag of dossieropslag in deze laag.
