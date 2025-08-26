# 🔐 **SUPPORT ADMINISTRATEUR GLOBAL - IMPORT DES PRIMES**

## 🎯 **PROBLÉMATIQUE RÉSOLUE**

L'**Administrateur Global** n'a pas de pays rattaché à son compte, contrairement aux **Administrateurs Territoriaux** et **Chefs de Département Technique**. Il doit pouvoir accéder aux primes de **tous les pays**.

## ✅ **SOLUTION IMPLÉMENTÉE**

### **1. Gestion des Permissions**

**Avant :**
```python
permission_classes = [IsAuthenticated, IsTerritorialAdmin | IsChefDeptTech]
```

**Après :**
```python
permission_classes = [IsAuthenticated, IsGlobalAdmin | IsTerritorialAdmin | IsChefDeptTech]
```

### **2. Logique de Filtrage par Pays**

#### **Service `PrimeLoaderService`**

**Méthode `_get_user_country()` :**
```python
def _get_user_country(self):
    """
    Récupère le pays de l'utilisateur connecté ou None pour l'admin global
    """
    # Vérifier si c'est un administrateur global
    if hasattr(self.user, 'global_admin') and self.user.global_admin:
        return None  # Admin global peut accéder à tous les pays
    
    # Vérifier les autres types d'utilisateurs avec pays
    if hasattr(self.user, 'territorial_admin') and self.user.territorial_admin.country:
        return self.user.territorial_admin.country
    elif hasattr(self.user, 'chef_dept_tech') and self.user.chef_dept_tech.country:
        return self.user.chef_dept_tech.country
    else:
        raise ValidationError("L'utilisateur n'est pas associé à un pays et n'est pas administrateur global")
```

#### **Méthode `find_client_by_name()` :**
```python
def find_client_by_name(self, client_name):
    """
    Trouve un client par nom exact dans le pays de l'utilisateur ou tous les pays pour l'admin global
    """
    try:
        # Pour l'admin global, rechercher dans tous les pays
        if self.user_country is None:
            client = Client.objects.filter(
                name__iexact=client_name
            ).first()
        else:
            # Pour les autres utilisateurs, filtrer par pays
            client = Client.objects.filter(
                name__iexact=client_name,
                country=self.user_country
            ).first()
        
        return client
    except Exception:
        return None
```

### **3. Vues API Adaptées**

#### **`ClientPrimeListView` :**
```python
# Récupérer les clients selon le type d'utilisateur
if prime_service.user_country is None:
    # Admin global : tous les clients
    clients = Client.objects.all().order_by('name')
else:
    # Autres utilisateurs : clients de leur pays
    clients = Client.objects.filter(
        country=prime_service.user_country
    ).order_by('name')
```

#### **`ClientPrimeHistoryView` :**
```python
# Récupérer le client selon le type d'utilisateur
if prime_service.user_country is None:
    # Admin global : peut accéder à tous les clients
    client = Client.objects.get(id=client_id)
else:
    # Autres utilisateurs : seulement les clients de leur pays
    client = Client.objects.get(
        id=client_id,
        country=prime_service.user_country
    )
```

## 🔄 **COMPORTEMENT PAR TYPE D'UTILISATEUR**

### **Administrateur Global**
- ✅ **Accès** : Tous les pays
- ✅ **Import** : Peut importer des primes pour tous les clients
- ✅ **Consultation** : Peut voir tous les clients et leur historique
- ✅ **Filtrage** : Aucun filtrage par pays

### **Administrateur Territorial**
- ✅ **Accès** : Seulement son pays assigné
- ✅ **Import** : Peut importer des primes pour les clients de son pays
- ✅ **Consultation** : Peut voir les clients de son pays
- ✅ **Filtrage** : Filtrage automatique par pays

### **Chef de Département Technique**
- ✅ **Accès** : Seulement son pays assigné
- ✅ **Import** : Peut importer des primes pour les clients de son pays
- ✅ **Consultation** : Peut voir les clients de son pays
- ✅ **Filtrage** : Filtrage automatique par pays

## 🎯 **AVANTAGES DE CETTE APPROCHE**

### **1. Cohérence avec l'Architecture Existante**
- ✅ **Même logique** que les services de statistiques clients
- ✅ **Réutilisation** des patterns existants
- ✅ **Maintenance** simplifiée

### **2. Sécurité Maintenue**
- ✅ **Permissions** strictes par type d'utilisateur
- ✅ **Filtrage** automatique selon les droits
- ✅ **Validation** des accès

### **3. Flexibilité**
- ✅ **Admin Global** : Accès complet
- ✅ **Utilisateurs Territoriaux** : Accès limité à leur pays
- ✅ **Extensibilité** : Facile d'ajouter d'autres types d'utilisateurs

## 📊 **EXEMPLES D'UTILISATION**

### **Admin Global - Import de Primes**
```bash
# L'admin global peut importer des primes pour n'importe quel client
curl -X POST \
  -H "Authorization: Bearer ADMIN_GLOBAL_TOKEN" \
  -F "file=@primes_tous_pays.xlsx" \
  http://localhost:8000/data/prime-import/
```

### **Admin Territorial - Import de Primes**
```bash
# L'admin territorial ne peut importer que pour son pays
curl -X POST \
  -H "Authorization: Bearer ADMIN_TERRITORIAL_TOKEN" \
  -F "file=@primes_mon_pays.xlsx" \
  http://localhost:8000/data/prime-import/
```

### **Consultation des Clients**
```bash
# Admin Global : Tous les clients
GET /data/prime-import/clients/
# Retourne tous les clients de tous les pays

# Admin Territorial : Clients de son pays
GET /data/prime-import/clients/
# Retourne seulement les clients de son pays assigné
```

## 🔧 **VALIDATION DES DOUBLONS**

### **Admin Global**
- ⚠️ **Détection** : Doublons de noms dans tous les pays
- ⚠️ **Alerte** : Si plusieurs clients avec le même nom existent

### **Admin Territorial**
- ⚠️ **Détection** : Doublons de noms dans son pays uniquement
- ⚠️ **Alerte** : Si plusieurs clients avec le même nom dans son pays

## 📝 **MESSAGES D'ERREUR ADAPTÉS**

### **Admin Global**
```
"Plusieurs clients trouvés avec le nom 'Entreprise ABC' dans différents pays"
```

### **Admin Territorial**
```
"Plusieurs clients trouvés avec le nom 'Entreprise ABC' dans votre pays"
```

## ✅ **RÉSULTAT FINAL**

Le service d'import des primes supporte maintenant **tous les types d'utilisateurs** :

1. **Administrateur Global** : Accès complet à tous les pays
2. **Administrateur Territorial** : Accès limité à son pays
3. **Chef de Département Technique** : Accès limité à son pays

La logique est **cohérente** avec l'architecture existante et **sécurisée** selon les permissions de chaque utilisateur.

---

**Le service d'import des primes est maintenant entièrement opérationnel pour tous les types d'utilisateurs !** 🚀
