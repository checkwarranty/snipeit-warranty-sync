<?php
require '/var/www/html/vendor/autoload.php';
$app = require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$settings = new App\Models\Setting();
$settings->site_name = 'Acceptance';
$settings->brand = 1;
$settings->full_multiple_companies_support = 0;
$settings->saveOrFail();
$user = App\Models\User::where('username', 'acceptance')->firstOrFail();
$token = $user->createToken('acceptance')->accessToken;
$category = new App\Models\Category();
$category->name = 'Acceptance Laptop';
$category->category_type = 'asset';
$category->saveOrFail();
$manufacturer = new App\Models\Manufacturer();
$manufacturer->name = 'Dell';
$manufacturer->saveOrFail();
$field = new App\Models\CustomField();
$field->name = 'Warranty Expiration';
$field->format = 'DATE';
$field->element = 'date_picker';
if (!$field->save()) { throw new RuntimeException('Cannot create acceptance custom field'); }
$fieldset = new App\Models\CustomFieldset();
$fieldset->name = 'Acceptance Warranty';
$fieldset->saveOrFail();
$fieldset->fields()->attach($field->id, ['required' => false, 'order' => 1]);
$model = new App\Models\AssetModel();
$model->name = 'Dell Latitude acceptance';
$model->model_number = 'Acceptance';
$model->category_id = $category->id;
$model->manufacturer_id = $manufacturer->id;
$model->fieldset_id = $fieldset->id;
$model->saveOrFail();
$status = new App\Models\Statuslabel();
$status->name = 'Acceptance ready';
$status->deployable = 1;
$status->pending = 0;
$status->archived = 0;
$status->saveOrFail();
$ids = [];
foreach (['ENDONLY', 'FULL', 'NOTFOUND', 'ASYNC'] as $kind) {
    $asset = new App\Models\Asset();
    $asset->asset_tag = 'ACCEPTANCE-' . $kind;
    $asset->serial = 'TEST-' . $kind;
    $asset->model_id = $model->id;
    $asset->status_id = $status->id;
    if ($kind === 'FULL') {
        $asset->purchase_date = '2020-03-01';
    }
    $asset->saveOrFail();
    $ids[$kind] = $asset->id;
}
file_put_contents('/tmp/cw-snipe-auth.json', json_encode(['token' => $token, 'field' => $field->db_column_name(), 'ids' => $ids]));
echo "Acceptance data seeded\n";
