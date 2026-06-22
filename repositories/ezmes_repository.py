class ezmes_repository:
    def __init__(self, session:AsyncSession):
        self.session = session
        
    