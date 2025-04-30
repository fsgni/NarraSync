document.addEventListener('DOMContentLoaded', () => {
    // --- Element References ---
    const statusDiv = document.getElementById('status');
    const scriptInput = document.getElementById('script-input');
    const speakerSelect = document.getElementById('speaker-select');
    const refreshSpeakersBtn = document.getElementById('refresh-speakers-btn');
    const processScriptBtn = document.getElementById('process-script-btn');
    const linePreviewArea = document.getElementById('line-preview-area');
    const audioPlayer = document.getElementById('audio-player');

    const dictEditorForm = document.getElementById('dict-editor-form');
    const surfaceInput = document.getElementById('surface');
    const pronunciationInput = document.getElementById('pronunciation');
    const accentTypeInput = document.getElementById('accent_type');
    const wordTypeSelect = document.getElementById('word_type');
    const priorityInput = document.getElementById('priority');
    const priorityValueSpan = document.getElementById('priority-value');
    const uuidInput = document.getElementById('uuid'); // Hidden input for UUID
    const addWordBtn = document.getElementById('add-word-btn');
    const updateWordBtn = document.getElementById('update-word-btn');
    const deleteWordBtn = document.getElementById('delete-word-btn');
    const clearFormBtn = document.getElementById('clear-form-btn');

    const refreshDictBtn = document.getElementById('refresh-dict-btn');
    const dictTbody = document.getElementById('dict-tbody');

    // --- API Helper ---
    async function fetchAPI(url, options = {}) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error! Status: ${response.status}` }));
                throw new Error(errorData.error || errorData.message || `Request failed with status ${response.status}`);
            }
            // Handle different response types
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.includes("application/json")) {
                return await response.json();
            } else if (contentType && contentType.includes("audio/")) {
                return await response.blob(); // Return audio blob
            } else {
                return await response.text(); // Or text for simple success messages
            }
        } catch (error) {
            console.error(`API Error (${url}):`, error);
            updateStatus(`错误: ${error.message}`, true);
            throw error; // Re-throw for calling function to handle
        }
    }

    // --- UI Update Functions ---
    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? 'red' : 'green';
        statusDiv.style.borderColor = isError ? 'red' : '#ccc';
        if (!isError) {
            // Optionally clear status after a few seconds if it's not an error
            // setTimeout(() => { if (statusDiv.textContent === message && !isError) statusDiv.textContent = ''; }, 5000);
        }
    }

    function populateSpeakers(speakers) {
        speakerSelect.innerHTML = '<option value="">-- 选择说话人 --</option>'; // Clear existing
        if (speakers && speakers.length > 0) {
            speakers.forEach(speaker => {
                const option = document.createElement('option');
                option.value = speaker.id;
                option.textContent = `${speaker.name} (ID: ${speaker.id})`;
                speakerSelect.appendChild(option);
            });
        } else {
             speakerSelect.innerHTML = '<option value="">无法加载说话人</option>';
        }
    }

    function populateDictionary(dictList) {
        dictTbody.innerHTML = ''; // Clear existing rows
        if (dictList && dictList.length > 0) {
            dictList.forEach(item => {
                const row = dictTbody.insertRow();
                row.insertCell().textContent = item.surface;
                row.insertCell().textContent = item.pronunciation;
                row.insertCell().textContent = item.accent_type;
                row.insertCell().textContent = item.word_type;
                row.insertCell().textContent = item.priority;
                row.insertCell().textContent = item.uuid;

                const actionsCell = row.insertCell();
                const editBtn = document.createElement('button');
                editBtn.textContent = '编辑';
                editBtn.onclick = () => populateFormForEdit(item);
                actionsCell.appendChild(editBtn);
            });
        } else {
            const row = dictTbody.insertRow();
            const cell = row.insertCell();
            cell.colSpan = 7;
            cell.textContent = '用户词典为空或加载失败。';
            cell.style.textAlign = 'center';
        }
    }

    function clearDictForm() {
        dictEditorForm.reset(); // Resets form elements to default values
        priorityValueSpan.textContent = priorityInput.value; // Reset slider display
        uuidInput.value = ''; // Clear hidden UUID
        updateWordBtn.disabled = true;
        deleteWordBtn.disabled = true;
        addWordBtn.disabled = false;
        surfaceInput.focus(); // Focus on the first field
    }

    function populateFormForEdit(dictItem) {
        surfaceInput.value = dictItem.surface;
        pronunciationInput.value = dictItem.pronunciation;
        accentTypeInput.value = dictItem.accent_type;
        wordTypeSelect.value = dictItem.word_type || 'PROPER_NOUN'; // Default if missing
        priorityInput.value = dictItem.priority;
        priorityValueSpan.textContent = dictItem.priority;
        uuidInput.value = dictItem.uuid;

        addWordBtn.disabled = true; // Disable Add when editing
        updateWordBtn.disabled = false; // Enable Update
        deleteWordBtn.disabled = false; // Enable Delete

        // Scroll to the form maybe?
        dictEditorForm.scrollIntoView({ behavior: 'smooth' });
    }

    // --- Event Handlers ---
    async function handleRefreshSpeakers() {
        updateStatus('正在刷新说话人列表...');
        try {
            const speakers = await fetchAPI('/api/speakers');
            populateSpeakers(speakers);
            updateStatus('说话人列表已刷新。');
        } catch (error) { /* Error handled in fetchAPI */ }
    }

    async function handleRefreshDictionary() {
        updateStatus('正在刷新用户词典...');
        dictTbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">加载中...</td></tr>';
        try {
            const dictList = await fetchAPI('/api/user_dict');
            populateDictionary(dictList);
            updateStatus('用户词典已刷新。');
        } catch (error) { /* Error handled in fetchAPI */ }
    }

    function handleProcessScript() {
        const scriptText = scriptInput.value.trim();
        const lines = scriptText.split(/\r?\n/).filter(line => line.trim() !== ''); // Split by newline, remove empty lines
        linePreviewArea.innerHTML = ''; // Clear previous lines

        if (lines.length === 0) {
            linePreviewArea.innerHTML = '<p style="color: grey;">请输入脚本并点击"处理脚本"。</p>';
            return;
        }

        lines.forEach((line, index) => {
            const lineDiv = document.createElement('div');
            lineDiv.dataset.lineIndex = index;
            lineDiv.dataset.lineText = line; // Store text for reuse

            const textSpan = document.createElement('span');
            textSpan.textContent = `${index + 1}: ${line}`;
            lineDiv.appendChild(textSpan);

            const controlsDiv = document.createElement('div');

            const playBtn = document.createElement('button');
            playBtn.textContent = '▶ 播放';
            playBtn.onclick = () => handlePlayLine(line, index);
            controlsDiv.appendChild(playBtn);

            // Add Edit Button (for potential dictionary addition/lookup later)
            // const editBtn = document.createElement('button');
            // editBtn.textContent = '编辑';
            // editBtn.onclick = () => { /* TODO: Implement dictionary lookup/edit based on line */ };
            // controlsDiv.appendChild(editBtn);

            lineDiv.appendChild(controlsDiv);
            linePreviewArea.appendChild(lineDiv);
        });
        updateStatus(`脚本已处理，共 ${lines.length} 行。`);
    }

    async function handlePlayLine(text, index) {
        const speakerId = speakerSelect.value;
        if (!speakerId) {
            updateStatus('请先选择一个说话人！', true);
            return;
        }

        const lineDiv = linePreviewArea.querySelector(`div[data-line-index="${index}"]`);
        const playBtn = lineDiv?.querySelector('button');
        const originalBtnText = playBtn ? playBtn.textContent : '▶ 播放';

        updateStatus(`正在生成第 ${index + 1} 行音频...`);
        if(playBtn) playBtn.textContent = '生成中...';
        if(playBtn) playBtn.disabled = true;
        audioPlayer.pause();
        audioPlayer.src = ''; // Clear previous audio

        try {
            const audioBlob = await fetchAPI('/api/generate_audio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, speaker_id: speakerId })
            });

            const audioUrl = URL.createObjectURL(audioBlob);
            audioPlayer.src = audioUrl;
            audioPlayer.play();
            updateStatus(`正在播放第 ${index + 1} 行。`);

        } catch (error) {
            // Error already shown by fetchAPI
             updateStatus(`生成第 ${index + 1} 行音频失败: ${error.message}`, true);
        } finally {
             if(playBtn) playBtn.textContent = originalBtnText;
             if(playBtn) playBtn.disabled = false;
        }
    }

    async function handleAddWord(event) {
        event.preventDefault(); // Prevent default form submission
        const surface = surfaceInput.value.trim();
        const pronunciation = pronunciationInput.value.trim();
        const accentType = accentTypeInput.value;
        const wordType = wordTypeSelect.value;
        const priority = priorityInput.value;

        if (!surface || !pronunciation) {
            updateStatus('表面形式和发音不能为空！', true);
            return;
        }

        updateStatus('正在添加词条...');
        addWordBtn.disabled = true;

        try {
            const result = await fetchAPI('/api/user_dict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ surface, pronunciation, accent_type: parseInt(accentType), word_type: wordType, priority: parseInt(priority) })
            });
            updateStatus(result.message || '词条添加成功！');
            clearDictForm();
            handleRefreshDictionary(); // Refresh the list
        } catch (error) {
             updateStatus(`添加词条失败: ${error.message}`, true);
             // Error message already shown by fetchAPI
        } finally {
            addWordBtn.disabled = false;
        }
    }

    // --- NEW: Event Handlers for Update and Delete ---
    async function handleUpdateWord(event) {
        event.preventDefault();
        const wordUuid = uuidInput.value;
        if (!wordUuid) {
            updateStatus('错误：未找到要更新的词条 UUID。', true);
            return;
        }

        const surface = surfaceInput.value.trim();
        const pronunciation = pronunciationInput.value.trim();
        const accentType = accentTypeInput.value;
        const wordType = wordTypeSelect.value;
        const priority = priorityInput.value;

        if (!surface || !pronunciation) {
            updateStatus('表面形式和发音不能为空！', true);
            return;
        }

        updateStatus('正在更新词条...');
        updateWordBtn.disabled = true;
        deleteWordBtn.disabled = true; // Disable delete too during update

        try {
            const result = await fetchAPI(`/api/user_dict/${wordUuid}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    surface, 
                    pronunciation, 
                    accent_type: parseInt(accentType), 
                    word_type: wordType, 
                    priority: parseInt(priority) 
                })
            });
            updateStatus(result.message || '词条更新成功！');
            clearDictForm();
            handleRefreshDictionary(); // Refresh the list
        } catch (error) {
            updateStatus(`更新词条失败: ${error.message}`, true);
            // Re-enable buttons on failure if needed (or rely on clearDictForm)
            updateWordBtn.disabled = false; 
            deleteWordBtn.disabled = false; 
        } finally {
             // Ensure buttons are re-enabled correctly after success/failure via clearDictForm
             // If clearDictForm was not called on error, re-enable here.
             // clearDictForm() handles button states, so this might be redundant
             // updateWordBtn.disabled = false; 
             // deleteWordBtn.disabled = false;
        }
    }

    async function handleDeleteWord(event) {
        event.preventDefault();
        const wordUuid = uuidInput.value;
        const surface = surfaceInput.value.trim() || `UUID: ${wordUuid}`;
        
        if (!wordUuid) {
            updateStatus('错误：未找到要删除的词条 UUID。', true);
            return;
        }

        // Confirmation dialog
        if (!confirm(`确定要删除词条 "${surface}" (UUID: ${wordUuid}) 吗？此操作无法撤销。`)) {
            return; // User cancelled
        }

        updateStatus('正在删除词条...');
        updateWordBtn.disabled = true; // Disable update during delete
        deleteWordBtn.disabled = true;

        try {
            const result = await fetchAPI(`/api/user_dict/${wordUuid}`, {
                method: 'DELETE'
            });
            updateStatus(result.message || '词条删除成功！');
            clearDictForm();
            handleRefreshDictionary(); // Refresh the list
        } catch (error) {
            updateStatus(`删除词条失败: ${error.message}`, true);
            // Re-enable buttons on failure
            updateWordBtn.disabled = false; 
            deleteWordBtn.disabled = false;
        } finally {
            // Ensure buttons are re-enabled correctly after success/failure via clearDictForm
            // updateWordBtn.disabled = false; 
            // deleteWordBtn.disabled = false;
        }
    }

    // --- Initial Load --- // Note: Added error handling for status check
    async function initializeApp() {
        updateStatus('正在检查 Voicevox 连接...');
        try {
            const statusData = await fetchAPI('/api/status');
            updateStatus(statusData.message);
            // If connected, load speakers and dictionary
            handleRefreshSpeakers();
            handleRefreshDictionary();
        } catch (error) {
            // If status check fails, the error is already shown by fetchAPI
            speakerSelect.innerHTML = '<option value="">连接失败</option>';
            dictTbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color: red;">连接 Voicevox 失败，请检查引擎是否运行。</td></tr>';
        }
    }

    // --- Event Listeners ---
    refreshSpeakersBtn.addEventListener('click', handleRefreshSpeakers);
    processScriptBtn.addEventListener('click', handleProcessScript);
    refreshDictBtn.addEventListener('click', handleRefreshDictionary);
    addWordBtn.addEventListener('click', handleAddWord);
    clearFormBtn.addEventListener('click', clearDictForm);
    priorityInput.addEventListener('input', () => {
        priorityValueSpan.textContent = priorityInput.value;
    });
    // Add listeners for updateWordBtn and deleteWordBtn
    updateWordBtn.addEventListener('click', handleUpdateWord);
    deleteWordBtn.addEventListener('click', handleDeleteWord);

    // --- Start the app ---
    initializeApp();

}); 