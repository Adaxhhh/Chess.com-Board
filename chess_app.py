import sys
import chess
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox
from PyQt5.QtCore import Qt, QRect, QPropertyAnimation, pyqtProperty, QEasingCurve, QPoint
from PyQt5.QtGui import QPainter, QBrush, QPixmap, QColor, QPen, QFont, QPixmapCache

# Mapping from python-chess piece symbols to your PNG filenames.
piece_images = {
    "P": "w_pawn.png",
    "R": "w_rook.png",
    "N": "w_knight.png",
    "B": "w_bishop.png",
    "Q": "w_queen.png",
    "K": "w_king.png",
    "p": "b_pawn.png",
    "r": "b_rook.png",
    "n": "b_knight.png",
    "b": "b_bishop.png",
    "q": "b_queen.png",
    "k": "b_king.png"
}

class ChessBoardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.square_size = 60
        self.board_size = self.square_size * 8
        self.setFixedSize(self.board_size, self.board_size)
        # Enable keyboard focus so we can capture arrow keys.
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Initialize python-chess board.
        self.board = chess.Board()
        print("Initial board FEN:", self.board.fen())
        self.selected_square = None
        self.loadPieceImages()
        
        # Move history: list of moves executed and current index.
        self.move_history = []
        self.current_move_index = 0

        # Animation-related attributes.
        self.animating = False
        self._anim_progress = 0.0
        self.pending_move = None
        self.anim_start_point = (0, 0)
        self.anim_end_point = (0, 0)
        self.anim = None
        
        # Bounce effects.
        self._bounce_scale = 1.0
        self.bounceAnim = None
        self._king_bounce_scale = 1.0
        self.kingBounceAnim = None

    def loadPieceImages(self):
        """Load and cache piece images for faster startup."""
        self.piece_pixmaps = {}
        for key, filename in piece_images.items():
            cached_pixmap = QPixmapCache.find(filename)
            if cached_pixmap is not None and not cached_pixmap.isNull():
                pixmap = cached_pixmap
            else:
                pixmap = QPixmap(filename)
                if pixmap.isNull():
                    print(f"Failed to load {filename} for piece {key}")
                    continue
                pixmap = pixmap.scaled(self.square_size, self.square_size,
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
                QPixmapCache.insert(filename, pixmap)
            self.piece_pixmaps[key] = pixmap

    @pyqtProperty(float)
    def anim_progress(self):
        return self._anim_progress

    @anim_progress.setter
    def anim_progress(self, value):
        self._anim_progress = value
        self.update()

    @pyqtProperty(float)
    def bounceScale(self):
        return self._bounce_scale

    @bounceScale.setter
    def bounceScale(self, value):
        self._bounce_scale = value
        self.update()

    @pyqtProperty(float)
    def kingBounceScale(self):
        return self._king_bounce_scale

    @kingBounceScale.setter
    def kingBounceScale(self, value):
        self._king_bounce_scale = value
        self.update()

    def resetBoardToIndex(self):
        """Reset the board to the starting position and push moves up to current_move_index."""
        self.board.reset()
        for move in self.move_history[:self.current_move_index]:
            self.board.push(move)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        # Set a very small font for board coordinates.
        coord_font = QFont("Arial", 7)
        painter.setFont(coord_font)

        light_color = QColor("#FFFFFF")
        dark_color = QColor("#3f6bd1")
        select_color = QColor(173, 216, 230, 150)

        # Draw board squares.
        for row in range(8):
            for col in range(8):
                rect = QRect(col * self.square_size, row * self.square_size,
                             self.square_size, self.square_size)
                color = light_color if (row + col) % 2 == 0 else dark_color
                painter.fillRect(rect, color)

        # Highlight king's square in light red if in check.
        if self.board.is_check():
            king_sq = self.board.king(self.board.turn)
            if king_sq is not None:
                king_col = chess.square_file(king_sq)
                king_row = 7 - chess.square_rank(king_sq)
                king_rect = QRect(king_col * self.square_size, king_row * self.square_size,
                                  self.square_size, self.square_size)
                painter.fillRect(king_rect, QColor(255, 200, 200, 150))

        # Highlight selected square.
        if self.selected_square is not None:
            col = chess.square_file(self.selected_square)
            row = 7 - chess.square_rank(self.selected_square)
            sel_rect = QRect(col * self.square_size, row * self.square_size,
                             self.square_size, self.square_size)
            painter.fillRect(sel_rect, select_color)

        # Highlight legal (non-capture) moves.
        if self.selected_square is not None and not self.animating:
            for move in self.board.legal_moves:
                if move.from_square == self.selected_square and not self.board.is_capture(move):
                    dest_sq = move.to_square
                    dest_col = chess.square_file(dest_sq)
                    dest_row = 7 - chess.square_rank(dest_sq)
                    legal_rect = QRect(dest_col * self.square_size, dest_row * self.square_size,
                                       self.square_size, self.square_size)
                    painter.setBrush(QColor(60, 60, 60, 100))
                    painter.setPen(Qt.NoPen)
                    center = legal_rect.center()
                    radius = self.square_size // 4.5
                    painter.drawEllipse(center, radius, radius)

        # Highlight capture targets with a transparent red hollow circle.
        if self.selected_square is not None and not self.animating:
            killable_squares = set()
            for move in self.board.legal_moves:
                if move.from_square == self.selected_square and self.board.is_capture(move):
                    if self.board.is_en_passant(move):
                        piece = self.board.piece_at(move.from_square)
                        if piece and piece.color == chess.WHITE:
                            captured_sq = move.to_square - 8
                        else:
                            captured_sq = move.to_square + 8
                    else:
                        captured_sq = move.to_square
                    killable_squares.add(captured_sq)
            pen = QPen(QColor(255, 0, 0, 150), 5, Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            for sq in killable_squares:
                col = chess.square_file(sq)
                row = 7 - chess.square_rank(sq)
                center = QPoint(col * self.square_size + self.square_size // 2,
                                row * self.square_size + self.square_size // 2)
                radius = self.square_size // 2 - 5
                painter.drawEllipse(center, radius, radius)

        # Draw pieces.
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece:
                if self.animating and self.pending_move:
                    if square == self.pending_move.from_square:
                        continue
                    if square == self.pending_move.to_square and self.board.piece_at(square) is not None:
                        if self.board.piece_at(square).color != self.board.turn:
                            continue
                symbol = piece.symbol()
                pixmap = self.piece_pixmaps.get(symbol)
                if pixmap:
                    col = chess.square_file(square)
                    row = 7 - chess.square_rank(square)
                    target_rect = QRect(col * self.square_size, row * self.square_size,
                                        self.square_size, self.square_size)
                    # Bounce the king if in check.
                    if piece.piece_type == chess.KING and piece.color == self.board.turn and self.board.is_check():
                        if self.kingBounceAnim is None:
                            self.startKingBounce()
                        painter.save()
                        center = target_rect.center()
                        painter.translate(center)
                        painter.scale(self.kingBounceScale, self.kingBounceScale)
                        painter.translate(-center)
                        painter.drawPixmap(target_rect, pixmap)
                        painter.restore()
                    # Bounce effect for selected piece.
                    elif square == self.selected_square and not self.animating:
                        painter.save()
                        center = target_rect.center()
                        painter.translate(center)
                        painter.scale(self.bounceScale, self.bounceScale)
                        painter.translate(-center)
                        painter.drawPixmap(target_rect, pixmap)
                        painter.restore()
                    else:
                        painter.drawPixmap(target_rect, pixmap)
                else:
                    print(f"No pixmap for piece {symbol} at square {square}")

        # Draw moving piece animation.
        if self.animating and self.pending_move:
            piece = self.board.piece_at(self.pending_move.from_square)
            if piece:
                symbol = piece.symbol()
                pixmap = self.piece_pixmaps.get(symbol)
                if pixmap:
                    start_x, start_y = self.anim_start_point
                    end_x, end_y = self.anim_end_point
                    current_x = start_x + (end_x - start_x) * self._anim_progress
                    current_y = start_y + (end_y - start_y) * self._anim_progress
                    target_rect = QRect(int(current_x), int(current_y),
                                        self.square_size, self.square_size)
                    painter.drawPixmap(target_rect, pixmap)

        # Draw board coordinates (very small letters on each square).
        painter.setPen(QColor("black"))
        coord_font.setPointSize(6)
        painter.setFont(coord_font)
        # Files (a-h) in the bottom-right corner of each square on bottom row.
        for col in range(8):
            file_letter = "abcdefgh"[col]
            x = col * self.square_size + self.square_size - 10
            y = 7 * self.square_size + self.square_size - 2
            painter.drawText(x, y, file_letter)
        # Ranks (8-1) in the top-left corner of each square on leftmost column.
        for row in range(8):
            rank_number = str(8 - row)
            x = 2
            y = row * self.square_size + 10
            painter.drawText(x, y, rank_number)

    def keyPressEvent(self, event):
        # Use arrow keys to navigate game history (undo/redo moves).
        if event.key() == Qt.Key_Left:
            if self.current_move_index > 0:
                self.current_move_index -= 1
                self.resetBoardToIndex()
        elif event.key() == Qt.Key_Right:
            if self.current_move_index < len(self.move_history):
                self.current_move_index += 1
                self.resetBoardToIndex()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.animating:
            return
        col = event.x() // self.square_size
        row = event.y() // self.square_size
        square = chess.square(col, 7 - row)
        if self.selected_square is None:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                self.selected_square = square
                self.bouncePiece()
                self.update()
        else:
            move = chess.Move(self.selected_square, square)
            if (self.board.piece_at(self.selected_square).piece_type == chess.PAWN and
                (chess.square_rank(square) == 0 or chess.square_rank(square) == 7)):
                move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)
            if move in self.board.legal_moves:
                self.startAnimation(move)
            self.selected_square = None
            self.update()

    def bouncePiece(self):
        self.bounceAnim = QPropertyAnimation(self, b"bounceScale")
        self.bounceAnim.setDuration(200)
        self.bounceAnim.setStartValue(1.0)
        self.bounceAnim.setKeyValueAt(0.5, 1.5)
        self.bounceAnim.setEndValue(1.0)
        self.bounceAnim.setEasingCurve(QEasingCurve.OutBounce)
        self.bounceAnim.start()

    def startKingBounce(self):
        if self.kingBounceAnim is None:
            self.kingBounceAnim = QPropertyAnimation(self, b"kingBounceScale")
            self.kingBounceAnim.setDuration(800)
            self.kingBounceAnim.setStartValue(1.0)
            self.kingBounceAnim.setKeyValueAt(0.5, 1.2)
            self.kingBounceAnim.setEndValue(1.0)
            self.kingBounceAnim.setLoopCount(-1)
            self.kingBounceAnim.start()

    def stopKingBounce(self):
        if self.kingBounceAnim:
            self.kingBounceAnim.stop()
            self.kingBounceAnim = None
            self._king_bounce_scale = 1.0

    def startAnimation(self, move):
        self.pending_move = move
        source_square = move.from_square
        dest_square = move.to_square
        source_col = chess.square_file(source_square)
        source_row = 7 - chess.square_rank(source_square)
        dest_col = chess.square_file(dest_square)
        dest_row = 7 - chess.square_rank(dest_square)
        self.anim_start_point = (source_col * self.square_size, source_row * self.square_size)
        self.anim_end_point = (dest_col * self.square_size, dest_row * self.square_size)
        self.animating = True
        self._anim_progress = 0.0
        self.anim = QPropertyAnimation(self, b"anim_progress")
        self.anim.setDuration(150)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.finished.connect(self.finishAnimation)
        self.anim.start()

    def finishAnimation(self):
        self.board.push(self.pending_move)
        # Discard any redo history if a new move is made.
        if self.current_move_index < len(self.move_history):
            self.move_history = self.move_history[:self.current_move_index]
        self.move_history.append(self.pending_move)
        self.current_move_index = len(self.move_history)
        self.pending_move = None
        self.animating = False
        if not self.board.is_check():
            self.stopKingBounce()
        self.update()
        self.checkGameStatus()

    def checkGameStatus(self):
        if self.board.is_checkmate():
            QMessageBox.information(self, "Game Over", "Checkmate!")
        elif self.board.is_stalemate():
            QMessageBox.information(self, "Game Over", "Stalemate!")
        elif self.board.is_insufficient_material():
            QMessageBox.information(self, "Game Over", "Draw by insufficient material.")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chess Game with History Navigation")
        self.chessBoardWidget = ChessBoardWidget()
        self.setCentralWidget(self.chessBoardWidget)
        self.setFixedSize(self.chessBoardWidget.width(), self.chessBoardWidget.height())

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
