set -euo pipefail
set -x

SUB="df765ee8-6e5a-4267-8829-97fd8ceea858"
LOCATION="centralus"
ENV="dev"
RG="rg-axlypro-${ENV}"
APP="fa-axlypro-${ENV}"
STORAGE="staxlyprodev${RANDOM}"
KV="kv-axlypro-${ENV}"
LAW="${APP}-law"
AI="${APP}-ai"

echo "Selecting subscription"
az account set --subscription "$SUB"

echo "Registering resource providers (this can take a few minutes)"
for RP in Microsoft.Resources Microsoft.Storage Microsoft.Web Microsoft.KeyVault Microsoft.ManagedIdentity Microsoft.OperationalInsights Microsoft.Insights; do
  az provider register --subscription "$SUB" -n "$RP" --wait
  az provider show --subscription "$SUB" -n "$RP" --query "{rp:name,state:registrationState}" -o table
done

echo "Creating storage"
az storage account create --subscription "$SUB" -g "$RG" -n "$STORAGE" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 --https-only true

echo "Creating Log Analytics"
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOCATION"
LAW_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query id -o tsv)

echo "Creating App Insights (workspace-based)"
az monitor app-insights component create -g "$RG" -l "$LOCATION" -a "$AI" --kind web --application-type web --workspace "$LAW_ID"
AI_CONN=$(az monitor app-insights component show -g "$RG" -a "$AI" --query connectionString -o tsv)

echo "Creating Function App"
az functionapp create --subscription "$SUB" -g "$RG" -n "$APP" --storage-account "$STORAGE" --consumption-plan-location "$LOCATION" --functions-version 4 --runtime python --runtime-version 3.11 --os-type Linux

echo "Assigning identity and base settings"
az functionapp identity assign -g "$RG" -n "$APP"
az functionapp config appsettings set -g "$RG" -n "$APP" --settings "APPLICATIONINSIGHTS_CONNECTION_STRING=$AI_CONN" "WEBSITE_RUN_FROM_PACKAGE=1" "PYTHON_ENABLE_WORKER_EXTENSIONS=1"

echo "Creating Key Vault"
az keyvault create -g "$RG" -n "$KV" -l "$LOCATION"

echo "Granting KV policy to Function App"
PRINCIPAL_ID=$(az functionapp identity show -g "$RG" -n "$APP" --query principalId -o tsv)
az keyvault set-policy --name "$KV" --object-id "$PRINCIPAL_ID" --secret-permissions get list

echo "Seeding secrets"
az keyvault secret set --vault-name "$KV" --name "OPENAI-API-KEY" --value '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'
az keyvault secret set --vault-name "$KV" --name "JWT-SECRET-KEY" --value 'kPksFzUAFexIuwOzOblOZK6YBHEbmTAg3oKG4tcLl5Q='
az keyvault secret set --vault-name "$KV" --name "AZURE-BLOB-CONN-STRING" --value 'DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;'
az keyvault secret set --vault-name "$KV" --name "AZURE-BLOB-CONTAINER" --value 'vehicle-images'

echo "Linking KV refs to Function App"
OPENAI_URI=$(az keyvault secret show --vault-name "$KV" --name "OPENAI-API-KEY" --query id -o tsv)
JWT_URI=$(az keyvault secret show --vault-name "$KV" --name "JWT-SECRET-KEY" --query id -o tsv)
BLOB_CONN_URI=$(az keyvault secret show --vault-name "$KV" --name "AZURE-BLOB-CONN-STRING" --query id -o tsv)
BLOB_CONTAINER_URI=$(az keyvault secret show --vault-name "$KV" --name "AZURE-BLOB-CONTAINER" --query id -o tsv)

az functionapp config appsettings set -g "$RG" -n "$APP" --settings "OPENAI_API_KEY=@Microsoft.KeyVault(SecretUri=$OPENAI_URI)" "JWT_SECRET_KEY=@Microsoft.KeyVault(SecretUri=$JWT_URI)" "AZURE_BLOB_CONN_STRING=@Microsoft.KeyVault(SecretUri=$BLOB_CONN_URI)" "AZURE_BLOB_CONTAINER=@Microsoft.KeyVault(SecretUri=$BLOB_CONTAINER_URI)"

echo "CORS"
az functionapp cors add --subscription "$SUB" -g "$RG" -n "$APP" --allowed-origins "http://localhost:3000" "https://dev.axly.pro" "http://localhost:19006" "http://127.0.0.1:19006" "http://10.0.2.2:19006" "http://10.0.2.2" "http://localhost" "http://127.0.0.1" "null"

echo "Host:"
az functionapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv
