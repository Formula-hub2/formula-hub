document.addEventListener('DOMContentLoaded', () => {
    send_query();
});

function send_query() {

    console.log("send query...")

    document.getElementById('results').innerHTML = '';
    document.getElementById("results_not_found").style.display = "none";
    console.log("hide not found icon");

    const filters = document.querySelectorAll('#filters input, #filters select, #filters [type="radio"]');

    filters.forEach(filter => {
        filter.addEventListener('input', () => {
            const csrfToken = document.getElementById('csrf_token').value;

            const searchCriteria = {
                csrf_token: csrfToken,
                query: document.querySelector('#query').value,
                publication_type: document.querySelector('#publication_type').value,
                sorting: document.querySelector('[name="sorting"]:checked').value,
            };

            console.log(document.querySelector('#publication_type').value);

            fetch('/explore', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(searchCriteria),
            })
                .then(response => response.json())
                .then(data => {

                    console.log(data);
                    document.getElementById('results').innerHTML = '';

                    // results counter
                    const resultCount = data.length;
                    const resultText = resultCount === 1 ? 'dataset' : 'datasets';
                    document.getElementById('results_number').textContent = `${resultCount} ${resultText} found`;

                    if (resultCount === 0) {
                        console.log("show not found icon");
                        document.getElementById("results_not_found").style.display = "block";
                    } else {
                        document.getElementById("results_not_found").style.display = "none";
                    }


                    data.forEach(dataset => {
                        let card = document.createElement('div');
                        card.className = 'col-12';
                        card.innerHTML = `
                            <div class="card">
                                <div class="card-body">
                                    <div class="d-flex align-items-center justify-content-between">
                                        <h3><a href="${dataset.dataset_doi ? dataset.url : '/dataset/view/' + dataset.id}">${dataset.title}</a></h3>
                                        <div>
                                            <span class="badge bg-primary" style="cursor: pointer;" onclick="set_publication_type_as_query('${dataset.publication_type}')">${dataset.publication_type}</span>
                                        </div>
                                    </div>
                                    <p class="text-secondary">${formatDate(dataset.created_at)}</p>

                                    <div class="row mb-2">

                                        <div class="col-md-4 col-12">
                                            <span class=" text-secondary">
                                                Description
                                            </span>
                                        </div>
                                        <div class="col-md-8 col-12">
                                            <p class="card-text">${dataset.description}</p>
                                        </div>

                                    </div>

                                    <div class="row mb-2">

                                        <div class="col-md-4 col-12">
                                            <span class=" text-secondary">
                                                Authors
                                            </span>
                                        </div>
                                        <div class="col-md-8 col-12">
                                            ${dataset.authors.map(author => `
                                                <p class="p-0 m-0">${author.name}${author.affiliation ? ` (${author.affiliation})` : ''}${author.orcid ? ` (${author.orcid})` : ''}</p>
                                            `).join('')}
                                        </div>

                                    </div>

                                    <div class="row mb-2">

                                        <div class="col-md-4 col-12">
                                            <span class=" text-secondary">
                                                Tags
                                            </span>
                                        </div>
                                        <div class="col-md-8 col-12">
                                            ${dataset.tags.map(tag => `<span class="badge bg-primary me-1" style="cursor: pointer;" onclick="set_tag_as_query('${tag}')">${tag}</span>`).join('')}
                                        </div>

                                    </div>

                                    <div class="row">

                                        <div class="col-md-4 col-12">

                                        </div>
                                        <div class="col-md-8 col-12">
                                            <a href="${dataset.url}" class="btn btn-outline-primary btn-sm" id="search" style="border-radius: 5px;">
                                                View dataset
                                            </a>
                                            <a href="/dataset/download/${dataset.id}" class="btn btn-outline-primary btn-sm" id="search" style="border-radius: 5px;">
                                                Download (${dataset.total_size_in_human_format})
                                            </a>
                                            <button
                                                class="btn btn-primary btn-sm btn-add-to-cart"
                                                data-dataset-id="${dataset.id}"
                                                data-dataset-title="${dataset.title}"
                                                id="add-btn-${dataset.id}"
                                                style="border-radius: 5px;"
                                            >
                                                <i data-feather="plus-circle" class="center-button-icon"></i>
                                                Add to my dataset
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;

                        document.getElementById('results').appendChild(card);

                        // Conecta el Add to my datasets con el carrito
                        const addBtn = document.getElementById(`add-btn-${dataset.id}`);
                        if (addBtn) {
                            addBtn.addEventListener('click', () => {
                                addDatasetToSelection(dataset.id, dataset.title);
                            });
                        }
                    });
                });
        });
    });
}

function formatDate(dateString) {
    const options = {day: 'numeric', month: 'long', year: 'numeric', hour: 'numeric', minute: 'numeric'};
    const date = new Date(dateString);
    return date.toLocaleString('en-US', options);
}

function set_tag_as_query(tagName) {
    const queryInput = document.getElementById('query');
    queryInput.value = tagName.trim();
    queryInput.dispatchEvent(new Event('input', {bubbles: true}));
}

function set_publication_type_as_query(publicationType) {
    const publicationTypeSelect = document.getElementById('publication_type');
    for (let i = 0; i < publicationTypeSelect.options.length; i++) {
        if (publicationTypeSelect.options[i].text === publicationType.trim()) {
            // Set the value of the select to the value of the matching option
            publicationTypeSelect.value = publicationTypeSelect.options[i].value;
            break;
        }
    }
    publicationTypeSelect.dispatchEvent(new Event('input', {bubbles: true}));
}

// Seleccion de datasets (Carrito)
const selectedDatasets = new Map(); // id -> title

function updateSelectedDatasetsUI() {
    const list = document.getElementById('selected-datasets-list');
    const badge = document.getElementById('cart-count-badge');
    const createBtn = document.getElementById('create-dataset-btn');
    const downloadBtn = document.getElementById('open-download-modal-btn');
    const hiddenInput = document.getElementById('selected-dataset-ids');
    const sidebarBadge = document.getElementById('dataset-sidebar-count');

    if (!list || !badge || !createBtn || !hiddenInput) return;

    list.innerHTML = '';

    if (selectedDatasets.size === 0) {
        const empty = document.createElement('li');
        empty.id = 'empty-cart-message';
        empty.className = 'list-group-item text-muted text-center';
        empty.textContent = 'No datasets selected yet.';
        list.appendChild(empty);
        createBtn.disabled = true;
        if(downloadBtn) downloadBtn.disabled = true;
    } else {
        selectedDatasets.forEach((title, id) => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            li.id = `selected-dataset-${id}`;

            const span = document.createElement('span');
            span.textContent = title;

            const removeBtn = document.createElement('button');
            removeBtn.className = 'btn btn-sm btn-outline-danger';
            removeBtn.textContent = 'Remove';
            removeBtn.addEventListener('click', () => {
                removeDatasetFromSelection(id);
            });

            li.appendChild(span);
            li.appendChild(removeBtn);
            list.appendChild(li);
        });

        createBtn.disabled = false;
        if(downloadBtn) downloadBtn.disabled = false;
    }

    badge.textContent = selectedDatasets.size;
    if (sidebarBadge) sidebarBadge.textContent = selectedDatasets.size;
    hiddenInput.value = Array.from(selectedDatasets.keys()).join(',');
}

function addDatasetToSelection(id, title) {
    const key = String(id);
    if (selectedDatasets.has(key)) {
        // Si ya está añadido:
        const existing = document.getElementById(`selected-dataset-${key}`);
        if (existing) {
            existing.classList.add('bg-warning');
            setTimeout(() => existing.classList.remove('bg-warning'), 300);
        }
        return;
    }

    selectedDatasets.set(key, title);

    const addBtn = document.getElementById(`add-btn-${key}`);
    if (addBtn) {
        addBtn.disabled = true;
        addBtn.textContent = 'Added';
    }

    updateSelectedDatasetsUI();
}

function removeDatasetFromSelection(id) {
    const key = String(id);
    if (!selectedDatasets.has(key)) return;

    selectedDatasets.delete(key);


    const addBtn = document.getElementById(`add-btn-${key}`);
    if (addBtn) {
        addBtn.disabled = false;
        addBtn.innerHTML = `<i data-feather="plus-circle" class="center-button-icon"></i> Add to my dataset`;
    }

    updateSelectedDatasetsUI();
}

document.getElementById('clear-filters').addEventListener('click', clearFilters);

function clearFilters() {

    // Reset the search query
    let queryInput = document.querySelector('#query');
    queryInput.value = "";
    // queryInput.dispatchEvent(new Event('input', {bubbles: true}));

    // Reset the publication type to its default value
    let publicationTypeSelect = document.querySelector('#publication_type');
    publicationTypeSelect.value = "any"; // replace "any" with whatever your default value is
    // publicationTypeSelect.dispatchEvent(new Event('input', {bubbles: true}));

    // Reset the sorting option
    let sortingOptions = document.querySelectorAll('[name="sorting"]');
    sortingOptions.forEach(option => {
        option.checked = option.value == "newest"; // replace "default" with whatever your default value is
        // option.dispatchEvent(new Event('input', {bubbles: true}));
    });

    // Perform a new search with the reset filters
    queryInput.dispatchEvent(new Event('input', {bubbles: true}));
}

document.addEventListener('DOMContentLoaded', () => {

    //let queryInput = document.querySelector('#query');
    //queryInput.dispatchEvent(new Event('input', {bubbles: true}));

    let urlParams = new URLSearchParams(window.location.search);
    let queryParam = urlParams.get('query');

    if (queryParam && queryParam.trim() !== '') {

        const queryInput = document.getElementById('query');
        queryInput.value = queryParam
        queryInput.dispatchEvent(new Event('input', {bubbles: true}));
        console.log("throw event");

    } else {
        const queryInput = document.getElementById('query');
        queryInput.dispatchEvent(new Event('input', {bubbles: true}));
    }

    // Modal close/cancel: Oculta el modal y permanece en la misma página
    function closeModalOnly() {
        const modal = document.getElementById('create-dataset-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    // Modal open: Muestra el modal cuando se clickea el botón "Create my own dataset"
    function openCreateDatasetModal() {
        const modal = document.getElementById('create-dataset-modal');
        if (modal) {
            modal.style.display = 'flex';
        }
    }



    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalCancelBtn = document.getElementById('modal-cancel-btn-text');
    const createDatasetBtn = document.getElementById('create-dataset-btn');

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModalOnly);
    if (modalCancelBtn) modalCancelBtn.addEventListener('click', closeModalOnly);
    if (createDatasetBtn) createDatasetBtn.addEventListener('click', openCreateDatasetModal);

    // EL carrito inicia sin datasets seleccionados
    updateSelectedDatasetsUI();

    document.getElementById('create-dataset-form').addEventListener('submit', function(e) {
        e.preventDefault();

        const formData = new FormData();
        const selectedDatasetIds = Array.from(selectedDatasets.keys()).join(',');

        formData.append('title', document.getElementById('dataset-title').value);
        formData.append('description', document.getElementById('dataset-description').value);
        formData.append('publication_type', document.getElementById('dataset-publication-type').value);
        formData.append('tags', document.getElementById('dataset-tags').value);
        formData.append('selected_datasets', selectedDatasetIds);
        formData.append('csrf_token', document.getElementById('csrf_token').value);

        // Maneja archivos si hay
        const fileInput = document.getElementById('dataset-files');
        if (fileInput.files.length > 0) {
            for (let i = 0; i < fileInput.files.length; i++) {
                formData.append('files', fileInput.files[i]);
            }
        }

        fetch('/explore/create-dataset-from-cart', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Vacia el carrito
                selectedDatasets.clear();
                updateSelectedDatasetsUI();

                // Cierra el modal
                closeModalOnly();

                const queryInput = document.getElementById('query');
                queryInput.dispatchEvent(new Event('input', {bubbles: true}));

            } else {
                alert('Error creating dataset: ' + data.message);
            }
        })
    });

    // Botón de Browse Files
    document.querySelector('button[style*="background-color: #69a7d6"]').addEventListener('click', function() {
        document.getElementById('dataset-files').click();
    });
});


document.addEventListener('DOMContentLoaded', () => {
    const dModal = document.getElementById('download-dataset-modal');
    const dOpenBtn = document.getElementById('open-download-modal-btn');
    const dCloseBtn = document.getElementById('download-modal-close-btn');
    const dForm = document.getElementById('download-dataset-form');

    if(dOpenBtn) dOpenBtn.onclick = () => dModal.style.display = 'flex';
    if(dCloseBtn) dCloseBtn.onclick = () => dModal.style.display = 'none';

    if(dForm) {
        dForm.onsubmit = function(e) {
            e.preventDefault();
            let filename = document.getElementById('zip-filename').value || "models";
            dModal.style.display = 'none';

            const csrfToken = document.getElementById('csrf_token').value;
            const datasetIds = Array.from(selectedDatasets.keys()).map(id => parseInt(id));

            fetch('/explore/download_cart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ dataset_ids: datasetIds, filename: filename })
            })
            .then(res => res.ok ? res.blob() : res.text().then(t => { throw new Error(t) }))
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename.endsWith('.zip') ? filename : filename + '.zip';
                document.body.appendChild(a);
                a.click();
                a.remove();
            })
            .catch(err => alert('Error downloading.'));
        };
    }
});
