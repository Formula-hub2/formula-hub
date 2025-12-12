/* app/modules/fakenodo/assets/scripts.js */

function test_fakenodo_connection() {
    var xhr = new XMLHttpRequest();
    // Endpoint para comprobar estado
    xhr.open('GET', '/fakenodo/test', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    
    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                try {
                    var response = JSON.parse(xhr.responseText);
                    console.log("Fakenodo Status:", response.message);
                    
                    if (!response.success) {
                        show_fakenodo_error();
                    }
                } catch (e) {
                    console.error("Error parsing JSON form Fakenodo:", e);
                }
            } else {
                console.error('Error connecting to Fakenodo:', xhr.status);
                show_fakenodo_error();
            }
        }
    };
    xhr.send();
}

function show_fakenodo_error() {
    var errorDiv = document.getElementById("test_zenodo_connection_error");
    if (errorDiv) {
        errorDiv.style.display = "block";
        errorDiv.innerText = "Error: Fakenodo service is not running correctly.";
    }
}

// === TRUCO DE COMPATIBILIDAD ===
// Creamos un alias: si alguien llama a 'test_zenodo_connection', 
// ejecutamos nuestra función de Fakenodo.
window.test_zenodo_connection = test_fakenodo_connection;
// ===============================

document.addEventListener("DOMContentLoaded", function() {
    test_fakenodo_connection();
});