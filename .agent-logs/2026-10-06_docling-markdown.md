Цель: сохранять Markdown Docling.
Файлы: backend/{storage,tasks,config,pipeline,tests}; docker-compose.yml; .env.example; docs/ARCHITECTURE.md.
Решение: атомарная запись по UUID в data/processed; ошибки записи завершают задачу с failed.
Риски: файлы вне Git; нужно контролировать место на диске.
