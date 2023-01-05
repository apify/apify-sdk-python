
"""
Copy-paste of method interfaces from Crawlee's implementation
constructor(options: DatasetOptions, readonly config = Configuration.getGlobalConfig()) {
    this.id = options.id;
    this.name = options.name;
    this.client = options.client.dataset(this.id) as DatasetClient<Data>;
}
async pushData(data: Data | Data[]): Promise<void>
async getData(options: DatasetDataOptions = {}): Promise<DatasetContent<Data>>
async exportTo(key: string, options?: ExportOptions, contentType?: string): Promise<void>
async exportToJSON(key: string, options?: Omit<ExportOptions, 'fromDataset'>)
async exportToCSV(key: string, options?: Omit<ExportOptions, 'fromDataset'>)
static async exportToJSON(key: string, options?: ExportOptions)
static async exportToCSV(key: string, options?: ExportOptions)
async getInfo(): Promise<DatasetInfo | undefined>
async forEach(iteratee: DatasetConsumer<Data>, options: DatasetIteratorOptions = {}, index = 0): Promise<void>
async map<R>(iteratee: DatasetMapper<Data, R>, options: DatasetIteratorOptions = {}): Promise<R[]>
async reduce<T>(iteratee: DatasetReducer<T, Data>, memo: T, options: DatasetIteratorOptions = {}): Promise<T>
async drop(): Promise<void>
static async open<Data extends Dictionary = Dictionary>(datasetIdOrName?: string | null, options: StorageManagerOptions = {}): Promise<Dataset<Data>>
static async pushData<Data extends Dictionary = Dictionary>(item: Data | Data[]): Promise<void>
static async getData<Data extends Dictionary = Dictionary>(options: DatasetDataOptions = {}): Promise<DatasetContent<Data>>
"""
class Dataset:
    pass
